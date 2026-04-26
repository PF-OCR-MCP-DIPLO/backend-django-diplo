import zipfile
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.documents.services.docx_image_extractor import (
    extract_images_in_order,
    extract_text_from_docx,
)
from apps.processing.models import ProcessRun, SourceImage
from apps.processing.services.diagnostics import stage_timer
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)


def create_process_run_from_upload(uploaded_file):
    _validate_uploaded_docx(uploaded_file)
    process_run = None
    created_image_paths = []
    runtime_config = get_runtime_config()
    try:
        with transaction.atomic():
            process_run = ProcessRun.objects.create(
                original_filename=uploaded_file.name,
                status=ProcessRun.Status.UPLOADED,
                provider_config_snapshot=as_snapshot_dict(runtime_config),
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
                    event["total_image_bytes"] = sum(
                        len(extracted.binary) for extracted in extracted_images
                    )
                    process_run.source_docx.seek(0)
                    extracted_text = extract_text_from_docx(process_run.source_docx)
                    event["docx_text_chars"] = len(extracted_text or "")
                process_run.extracted_text = extracted_text
                process_run.save(update_fields=["extracted_text", "updated_at"])
            except (zipfile.BadZipFile, KeyError, ValueError) as error:
                raise UploadValidationError(
                    code="invalid_docx",
                    message="El archivo .docx no es valido o esta corrupto.",
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
                    content_hash=sha256(extracted.binary).hexdigest(),
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
                }
                from apps.processing.services.diagnostics import record_processing_event

                record_processing_event(
                    process_run=process_run,
                    source_image=source_image,
                    stage="source_image_created",
                    status="completed",
                    runtime_config=runtime_config,
                    image_bytes=len(extracted.binary),
                    raw_payload=stage_payload,
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
    def __init__(self, *, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _build_image_filename(process_run_id, sequence_index, source_name):
    suffix = Path(source_name).suffix or ".bin"
    return f"process_runs/{process_run_id}/images/{sequence_index:04d}{suffix}"


def _validate_uploaded_docx(uploaded_file):
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
