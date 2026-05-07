"""Servicios de carga y descomposición inicial de documentos DOCX.

Transforma un archivo subido en una corrida persistida, extrae texto e imágenes
y registra trazabilidad para el pipeline posterior.
"""

import json
import logging
import zipfile
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.documents.services.docx_image_extractor import (
    DocxUnsupportedContentError,
    extract_images_in_order,
    extract_text_from_docx,
)
from apps.processing.models import ProcessRun, SourceImage
from apps.processing.services.diagnostics import record_processing_event, stage_timer
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)

logger = logging.getLogger(__name__)
PIPELINE_QUALITY_VERSION = "docx-context-conservative-fallback-v2"


def create_process_run_from_upload(uploaded_file):
    """Crea una corrida a partir de un DOCX subido por la API.

    Args:
        uploaded_file: Archivo DOCX recibido por la vista de upload.

    Returns:
        Instancia de `ProcessRun` persistida con imágenes fuente y texto del
        documento.

    Side Effects:
        Escribe el DOCX y las imágenes extraídas en storage, crea filas de
        `SourceImage` y borra artefactos parciales si ocurre un error.

    Raises:
        UploadValidationError: Si el archivo no cumple formato, tamaño o
            contenido esperado.
    """
    _validate_uploaded_docx(uploaded_file)
    runtime_config = get_runtime_config()
    upload_bytes_hash = _hash_uploaded_file(uploaded_file)
    provider_snapshot = as_snapshot_dict(runtime_config)
    processing_fingerprint = _build_processing_fingerprint(
        upload_bytes_hash, provider_snapshot
    )
    reused = _find_reusable_process_run(upload_bytes_hash, processing_fingerprint)
    if reused is not None:
        logger.info(
            "Reusing existing process run %s for duplicate upload %s",
            reused.pk,
            uploaded_file.name,
        )
        record_processing_event(
            process_run=reused,
            stage="existing_job_reused",
            status="completed",
            runtime_config=runtime_config,
            raw_payload={
                "source_docx_hash": upload_bytes_hash,
                "processing_fingerprint": processing_fingerprint,
                "original_filename": uploaded_file.name,
                "status": reused.status,
            },
            notes="Existing identical job reused; duplicate upload did not create a new run.",
        )
        if reused.status in {ProcessRun.Status.UPLOADED, ProcessRun.Status.PROCESSING}:
            record_processing_event(
                process_run=reused,
                stage="duplicate_http_request_ignored",
                status="completed",
                runtime_config=runtime_config,
                raw_payload={
                    "source_docx_hash": upload_bytes_hash,
                    "processing_fingerprint": processing_fingerprint,
                    "status": reused.status,
                },
                notes="Duplicate upload request ignored; existing active job was returned.",
            )
        reused._was_reused = True
        return reused

    process_run = None
    created_image_paths = []
    try:
        with transaction.atomic():
            process_run = ProcessRun.objects.create(
                original_filename=uploaded_file.name,
                status=ProcessRun.Status.UPLOADED,
                provider_config_snapshot=provider_snapshot,
                source_docx_hash=upload_bytes_hash,
                processing_fingerprint=processing_fingerprint,
            )
            uploaded_file.seek(0)
            process_run.source_docx.save(uploaded_file.name, uploaded_file, save=True)
            process_run.source_docx.open("rb")
            try:
                with stage_timer(
                    process_run=process_run,
                    stage="docx_extract_images",
                    runtime_config=runtime_config,
                    raw_payload={"filename": uploaded_file.name},
                ) as event:
                    extracted_images = extract_images_in_order(process_run.source_docx)
                    event["images_extracted"] = len(extracted_images)
                    event["duplicate_image_references_skipped"] = sum(
                        len(extracted.skipped_duplicate_sources or [])
                        for extracted in extracted_images
                    )
                    event["total_image_bytes"] = sum(
                        len(extracted.binary) for extracted in extracted_images
                    )
                    process_run.source_docx.seek(0)
                    extracted_text = extract_text_from_docx(process_run.source_docx)
                    event["docx_text_chars"] = len(extracted_text or "")
                _handle_image_limit_policy(
                    process_run,
                    runtime_config,
                    len(extracted_images),
                )
                process_run.extracted_text = extracted_text
                process_run.save(update_fields=["extracted_text", "updated_at"])
            except zipfile.BadZipFile as error:
                raise UploadValidationError(
                    code="invalid_docx",
                    message="El archivo .docx no es valido o esta corrupto.",
                    details={"reason": str(error)},
                ) from error
            except KeyError as error:
                raise UploadValidationError(
                    code="docx_unsupported_content",
                    message=(
                        "El archivo .docx es valido, pero no contiene la estructura "
                        "principal de Word que este extractor soporta."
                    ),
                    details={"reason": str(error)},
                ) from error
            except DocxUnsupportedContentError as error:
                raise UploadValidationError(
                    code="docx_unsupported_content",
                    message=(
                        "El archivo .docx es valido, pero contiene elementos que "
                        "no se pueden procesar con la configuracion actual."
                    ),
                    details={"reason": str(error)},
                ) from error
            except ValueError as error:
                raise UploadValidationError(
                    code="docx_conversion_error",
                    message=(
                        "El archivo .docx es valido, pero fallo la extraccion de "
                        "contenido para procesamiento."
                    ),
                    details={"reason": str(error)},
                ) from error
            finally:
                process_run.source_docx.close()
            if not extracted_images:
                raise UploadValidationError(
                    code="docx_no_images",
                    message="El archivo .docx no contiene imagenes embebidas para procesar.",
                )
            for extracted in extracted_images:
                filename = _build_image_filename(
                    process_run.id, extracted.sequence_index, extracted.source_name
                )
                source_image = SourceImage(
                    process_run=process_run,
                    sequence_index=extracted.sequence_index,
                    source_name=extracted.source_name,
                    content_hash=extracted.content_hash
                    or sha256(extracted.binary).hexdigest(),
                    context_date=extracted.context_date_normalized,
                    context_text=extracted.context_heading_text,
                    context_payload={
                        "context_date_text": extracted.context_date_text,
                        "context_date_normalized": (extracted.context_date_normalized),
                        "context_heading_text": extracted.context_heading_text,
                        "paragraph_index": extracted.paragraph_index,
                        "run_index": extracted.run_index,
                        "raw_reference_index": extracted.raw_reference_index,
                    },
                    ocr_status=SourceImage.OCRStatus.PENDING,
                )
                source_image.image_file.save(
                    filename, ContentFile(extracted.binary), save=True
                )
                created_image_paths.append(source_image.image_file.name)
                stage_payload = {
                    "image_bytes": len(extracted.binary),
                    "content_hash": source_image.content_hash,
                    "source_name": source_image.source_name,
                    "relationship_id": extracted.relationship_id,
                    "package_target": extracted.package_target,
                    "context_date": source_image.context_date,
                    "context_text": source_image.context_text,
                    "context_payload": source_image.context_payload,
                }
                record_processing_event(
                    process_run=process_run,
                    source_image=source_image,
                    stage="source_image_created",
                    status="completed",
                    runtime_config=runtime_config,
                    image_bytes=len(extracted.binary),
                    raw_payload=stage_payload,
                )
                for skipped in extracted.skipped_duplicate_sources or []:
                    logger.info(
                        "Skipping duplicate DOCX image reference for job %s: %s duplicates %s by %s",
                        process_run.pk,
                        skipped.get("source_name"),
                        source_image.source_name,
                        skipped.get("reason"),
                    )
                    record_processing_event(
                        process_run=process_run,
                        source_image=source_image,
                        stage="source_image_duplicate_skipped",
                        status="completed",
                        runtime_config=runtime_config,
                        raw_payload={
                            **skipped,
                            "kept_source_name": source_image.source_name,
                            "kept_source_image_id": source_image.pk,
                        },
                        notes=(
                            f"Skipped duplicate image reference {skipped.get('source_name')} "
                            f"because it matched {source_image.source_name} by "
                            f"{skipped.get('reason')}."
                        ),
                    )
            process_run.total_images = len(extracted_images)
            process_run.save(update_fields=["total_images", "updated_at"])
        return process_run
    except Exception:
        if process_run is not None:
            for image_path in created_image_paths:
                process_run.source_docx.storage.delete(image_path)
            process_run.source_docx.delete(save=False)
            process_run.delete()
        raise


class UploadValidationError(Exception):
    """Error de dominio para rechazos de upload antes de persistir la corrida."""

    def __init__(self, *, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _build_image_filename(process_run_id, sequence_index, source_name):
    suffix = Path(source_name).suffix or ".bin"
    return f"process_runs/{process_run_id}/images/{sequence_index:04d}{suffix}"


def _hash_uploaded_file(uploaded_file):
    uploaded_file.seek(0)
    digest = sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def _build_processing_fingerprint(source_hash, provider_snapshot):
    relevant_config = {
        "source_docx_hash": source_hash,
        "ocr_mode": provider_snapshot.get("ocr_mode"),
        "ocr_provider": provider_snapshot.get("ocr_provider"),
        "ocr_model": provider_snapshot.get("ocr_model"),
        "vision_model": provider_snapshot.get("vision_model"),
        "llm_provider": provider_snapshot.get("llm_provider"),
        "llm_model": provider_snapshot.get("llm_model"),
        "valid_consignation_month": provider_snapshot.get("valid_consignation_month"),
        "valid_consignation_year": provider_snapshot.get("valid_consignation_year"),
        "extraction_criteria": provider_snapshot.get("extraction_criteria"),
        "max_images_warning_threshold": provider_snapshot.get(
            "max_images_warning_threshold"
        ),
        "block_documents_over_image_limit": provider_snapshot.get(
            "block_documents_over_image_limit"
        ),
        "pipeline_quality_version": PIPELINE_QUALITY_VERSION,
    }
    encoded = json.dumps(relevant_config, sort_keys=True, default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


def _find_reusable_process_run(source_hash, processing_fingerprint):
    reusable_statuses = [
        ProcessRun.Status.UPLOADED,
        ProcessRun.Status.PROCESSING,
        ProcessRun.Status.COMPLETED,
    ]
    return (
        ProcessRun.objects.filter(
            source_docx_hash=source_hash,
            processing_fingerprint=processing_fingerprint,
            status__in=reusable_statuses,
        )
        .order_by("-created_at")
        .first()
    )


def _handle_image_limit_policy(process_run, runtime_config, image_count):
    threshold = int(runtime_config.max_images_warning_threshold or 0)
    if threshold <= 0 or image_count <= threshold:
        return
    message = (
        f"El documento contiene {image_count} imagenes, supera el limite "
        f"recomendado de {threshold}. "
    )
    if runtime_config.block_documents_over_image_limit:
        logger.warning("%sSe bloqueara el procesamiento por configuracion.", message)
        record_processing_event(
            process_run=process_run,
            stage="docx_image_limit_blocked",
            status="failed",
            runtime_config=runtime_config,
            raw_payload={
                "images_extracted": image_count,
                "max_images_warning_threshold": threshold,
                "block_documents_over_image_limit": True,
            },
            notes=f"{message}Se bloqueo el procesamiento por configuracion.",
        )
        raise UploadValidationError(
            code="docx_too_many_images",
            message=(
                "El archivo .docx es valido, pero supera el limite de imagenes "
                "configurado para bloquear el procesamiento."
            ),
            details={
                "images_extracted": image_count,
                "max_images_warning_threshold": threshold,
                "block_documents_over_image_limit": True,
            },
        )
    logger.warning("%sSe continuara el procesamiento.", message)
    record_processing_event(
        process_run=process_run,
        stage="docx_image_limit_warning",
        status="completed",
        runtime_config=runtime_config,
        raw_payload={
            "images_extracted": image_count,
            "max_images_warning_threshold": threshold,
            "block_documents_over_image_limit": False,
        },
        notes=f"{message}Se continuara el procesamiento.",
    )


def _validate_uploaded_docx(uploaded_file):
    """Verifica tamaño, extensión y firma ZIP del DOCX antes de procesarlo."""
    max_size = int(getattr(settings, "DOCX_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    if getattr(uploaded_file, "size", 0) > max_size:
        raise UploadValidationError(
            code="file_too_large",
            message="El archivo .docx excede el tamano maximo permitido.",
            details={"max_bytes": max_size},
        )
    if not uploaded_file.name.lower().endswith(".docx"):
        raise UploadValidationError(
            code="invalid_extension",
            message="Solo se permiten archivos .docx.",
        )
    uploaded_file.seek(0)
    signature = uploaded_file.read(4)
    uploaded_file.seek(0)
    if signature != b"PK\x03\x04":
        raise UploadValidationError(
            code="invalid_docx",
            message="El archivo .docx no es valido o esta corrupto.",
            details={"reason": "Invalid ZIP signature."},
        )
    if not zipfile.is_zipfile(uploaded_file):
        uploaded_file.seek(0)
        raise UploadValidationError(
            code="invalid_docx",
            message="El archivo .docx no es valido o esta corrupto.",
            details={"reason": "Invalid ZIP container."},
        )
    uploaded_file.seek(0)
