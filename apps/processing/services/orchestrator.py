"""Orquestación del pipeline de procesamiento de consignaciones.

Este módulo coordina preparación de corridas, ejecución OCR/LLM, registro de
logs técnicos y consolidación de contadores de estado.
"""

import time

from django.db import transaction
from django.utils import timezone

from apps.processing.models import (
    ExtractionLog,
    ProcessRun,
    SourceImage,
)
from apps.processing.services.agents import ProcessingSupervisorAgent
from apps.processing.services.diagnostics import record_processing_event, stage_timer
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)

DOCUMENT_TEXT_SOURCE_NAME = "document_text"


def is_generated_text_source(source_image):
    """Indica si la fila representa texto extraído del documento y no una imagen real."""
    return (
        source_image is not None
        and source_image.sequence_index == 0
        and source_image.source_name == DOCUMENT_TEXT_SOURCE_NAME
    )


def real_source_images_queryset(process_run):
    """Devuelve las imágenes realmente procesables del job.

    La fuente `document_text` con `sequence_index=0` se usa como contexto interno
    y no debe entrar al conteo de imágenes procesables.
    """
    return process_run.source_images.exclude(
        sequence_index=0,
        source_name=DOCUMENT_TEXT_SOURCE_NAME,
    ).exclude(image_file="")


def _create_log(process_run, source_image, stage, runtime_config, **kwargs):
    status = kwargs.get("status") or (
        "failed" if kwargs.get("is_error", False) else "completed"
    )
    return record_processing_event(
        process_run=process_run,
        source_image=source_image,
        stage=stage,
        status=status,
        runtime_config=runtime_config,
        provider=kwargs.get("provider", ""),
        model=kwargs.get("model", ""),
        raw_payload=kwargs.get("raw_payload", {}),
        raw_text=kwargs.get("raw_text", ""),
        notes=kwargs.get("notes", ""),
    )


def _safe_create_log(process_run, source_image, stage, runtime_config, **kwargs):
    try:
        return _create_log(process_run, source_image, stage, runtime_config, **kwargs)
    except Exception:
        return None


def _build_runtime_snapshot(runtime_config):
    snapshot = as_snapshot_dict(runtime_config)
    snapshot["extraction_criteria"] = runtime_config.extraction_criteria
    return snapshot


def _sync_job_counters(process_run):
    process_run.total_images = real_source_images_queryset(process_run).count()
    process_run.total_records = process_run.deposits.count()
    process_run.save(update_fields=["total_images", "total_records", "updated_at"])
    return process_run


def prepare_job_for_full_processing(process_run):
    """Reinicia una corrida para reprocesarla de forma completa."""
    runtime_config = get_runtime_config()
    process_run = ProcessRun.objects.get(pk=process_run.pk)
    with stage_timer(
        process_run=process_run,
        stage="job_prepare",
        runtime_config=runtime_config,
    ) as event:
        with transaction.atomic():
            generated_text_images = process_run.source_images.filter(
                sequence_index=0, source_name=DOCUMENT_TEXT_SOURCE_NAME
            )
            generated_text_images.delete()
            process_run.deposits.all().delete()
            process_run.extraction_logs.exclude(stage__startswith="docx_").exclude(
                stage="source_image_created"
            ).delete()
            if process_run.excel_file:
                process_run.excel_file.delete(save=False)
                process_run.excel_file = None
            process_run.status = ProcessRun.Status.PROCESSING
            process_run.started_at = timezone.now()
            process_run.finished_at = None
            process_run.error_message = ""
            process_run.total_images = real_source_images_queryset(process_run).count()
            process_run.total_records = 0
            process_run.provider_config_snapshot = _build_runtime_snapshot(
                runtime_config
            )
            process_run.save(
                update_fields=[
                    "status",
                    "started_at",
                    "finished_at",
                    "error_message",
                    "total_images",
                    "total_records",
                    "excel_file",
                    "provider_config_snapshot",
                    "updated_at",
                ]
            )
            real_source_images_queryset(process_run).update(
                ocr_status=SourceImage.OCRStatus.PENDING,
                ocr_raw_text="",
                error_message="",
                ocr_provider=runtime_config.ocr_provider,
            )
            event["total_images"] = process_run.total_images
    return process_run, runtime_config


def prepare_job_for_processing(process_run):
    """Compatibilidad semántica con el preparador principal del pipeline."""
    return prepare_job_for_full_processing(process_run)


def mark_job_failed(job_id, error, runtime_config=None):
    """Marca una corrida como fallida y persiste el mensaje de error."""
    process_run = ProcessRun.objects.filter(pk=job_id).first()
    if process_run is None:
        return None
    message = str(error)
    process_run.status = ProcessRun.Status.FAILED
    process_run.error_message = message
    process_run.finished_at = timezone.now()
    process_run.save(
        update_fields=["status", "error_message", "finished_at", "updated_at"]
    )
    if runtime_config is not None:
        _safe_create_log(
            process_run,
            None,
            "job_failed",
            runtime_config,
            notes=message,
            is_error=True,
        )
    return process_run


def process_prepared_job(process_run, runtime_config):
    """Ejecuta OCR y estructuración sobre todas las imágenes de una corrida."""
    supervisor = ProcessingSupervisorAgent()
    fatal_error = ""
    failed_images = 0
    ocr_calls = 0
    llm_calls = 0
    record_processing_event(
        process_run=process_run,
        stage="job_started",
        status="completed",
        runtime_config=runtime_config,
        raw_payload={
            "job_id": process_run.pk,
            "total_images": real_source_images_queryset(process_run).count(),
            "process_extracted_text": False,
        },
        notes=(
            "Supervisor processing started. extracted_text is retained as "
            "document context and is not structured by default."
        ),
    )
    final_status = ProcessRun.Status.FAILED
    try:
        real_images = real_source_images_queryset(process_run).order_by(
            "sequence_index", "id"
        )
        for source_image in real_images:
            started_at = time.monotonic()
            try:
                with stage_timer(
                    process_run=process_run,
                    source_image=source_image,
                    stage="image_processing",
                    runtime_config=runtime_config,
                    raw_payload={"source_name": source_image.source_name},
                ) as event:
                    records_count = supervisor.process_image(
                        process_run,
                        source_image,
                        runtime_config,
                        _safe_create_log,
                    )
                    event["records_count"] = records_count
                ocr_calls += 1
                llm_calls += 1
                _safe_create_log(
                    process_run,
                    source_image,
                    "image_processed",
                    runtime_config,
                    provider=source_image.ocr_provider,
                    model=runtime_config.llm_model,
                    raw_payload={
                        "job_id": process_run.pk,
                        "source_image_id": source_image.pk,
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "records_count": source_image.deposits.count(),
                        "persisted_records_count": source_image.deposits.count(),
                    },
                    notes=(
                        "Image processed successfully"
                        if source_image.deposits.count() > 0
                        else "Image processed with 0 persisted records"
                    ),
                )
            except Exception as error:
                failed_images += 1
                source_image.ocr_status = SourceImage.OCRStatus.FAILED
                source_image.error_message = str(error)
                source_image.save(
                    update_fields=[
                        "ocr_status",
                        "error_message",
                        "ocr_provider",
                        "updated_at",
                    ]
                )
                _safe_create_log(
                    process_run,
                    source_image,
                    "image_failed",
                    runtime_config,
                    provider=source_image.ocr_provider,
                    model=runtime_config.ocr_model,
                    raw_payload={
                        "job_id": process_run.pk,
                        "source_image_id": source_image.pk,
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                    },
                    notes=str(error),
                    is_error=True,
                )
                if not fatal_error:
                    fatal_error = str(error)
        total_records = process_run.deposits.count()
        total_images = real_source_images_queryset(process_run).count()
        if fatal_error and total_records == 0 and failed_images >= total_images:
            final_status = ProcessRun.Status.FAILED
        elif fatal_error or failed_images > 0:
            final_status = ProcessRun.Status.COMPLETED_WITH_ERRORS
        else:
            final_status = ProcessRun.Status.COMPLETED
        if total_images > 0 and failed_images == total_images and total_records == 0:
            final_status = ProcessRun.Status.FAILED
    except Exception as error:
        fatal_error = str(error)
        final_status = ProcessRun.Status.FAILED
        _safe_create_log(
            process_run,
            None,
            "job_failed",
            runtime_config,
            notes=fatal_error,
            is_error=True,
        )
    finally:
        process_run.refresh_from_db()
        process_run.total_images = real_source_images_queryset(process_run).count()
        process_run.total_records = process_run.deposits.count()
        process_run.finished_at = timezone.now()
        process_run.status = final_status
        process_run.error_message = fatal_error
        process_run.save(
            update_fields=[
                "total_images",
                "total_records",
                "finished_at",
                "status",
                "error_message",
                "updated_at",
            ]
        )
        _safe_create_log(
            process_run,
            None,
            "job_finished",
            runtime_config,
            status="completed",
            raw_payload={
                "job_id": process_run.pk,
                "status": process_run.status,
                "total_images": process_run.total_images,
                "total_records": process_run.total_records,
                "failed_images": failed_images,
                "number_of_ocr_calls": ocr_calls,
                "number_of_llm_calls": llm_calls,
            },
            notes=f"status={process_run.status}",
            is_error=process_run.status == ProcessRun.Status.FAILED,
        )
    return process_run


def process_job(process_run):
    """Atajo de compatibilidad para preparar y ejecutar una corrida completa."""
    prepared_job, runtime_config = prepare_job_for_full_processing(process_run)
    return process_prepared_job(prepared_job, runtime_config)
