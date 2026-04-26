import time

from django.db import transaction
from django.utils import timezone

from apps.processing.models import (
    ExtractionLog,
    ProcessRun,
    SourceImage,
)
from apps.processing.services.agents import ProcessingSupervisorAgent
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)

DOCUMENT_TEXT_SOURCE_NAME = "document_text"


def is_generated_text_source(source_image):
    return (
        source_image is not None
        and source_image.sequence_index == 0
        and source_image.source_name == DOCUMENT_TEXT_SOURCE_NAME
    )


def real_source_images_queryset(process_run):
    return process_run.source_images.exclude(
        sequence_index=0,
        source_name=DOCUMENT_TEXT_SOURCE_NAME,
    ).exclude(image_file="")


def _create_log(process_run, source_image, stage, runtime_config, **kwargs):
    sequence_index = source_image.sequence_index if source_image else 0
    return ExtractionLog.objects.create(
        process_run=process_run,
        source_image=source_image,
        sequence_index=sequence_index,
        stage=stage,
        ocr_mode=runtime_config.ocr_mode,
        provider=kwargs.get("provider", ""),
        model=kwargs.get("model", ""),
        raw_payload=kwargs.get("raw_payload", {}),
        raw_text=kwargs.get("raw_text", ""),
        notes=kwargs.get("notes", ""),
        is_error=kwargs.get("is_error", False),
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
    runtime_config = get_runtime_config()
    process_run = ProcessRun.objects.get(pk=process_run.pk)
    with transaction.atomic():
        generated_text_images = process_run.source_images.filter(
            sequence_index=0, source_name=DOCUMENT_TEXT_SOURCE_NAME
        )
        generated_text_images.delete()
        process_run.deposits.all().delete()
        process_run.extraction_logs.all().delete()
        if process_run.excel_file:
            process_run.excel_file.delete(save=False)
            process_run.excel_file = None
        process_run.status = ProcessRun.Status.PROCESSING
        process_run.started_at = timezone.now()
        process_run.finished_at = None
        process_run.error_message = ""
        process_run.total_images = real_source_images_queryset(process_run).count()
        process_run.total_records = 0
        process_run.provider_config_snapshot = _build_runtime_snapshot(runtime_config)
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
    return process_run, runtime_config


def prepare_job_for_processing(process_run):
    return prepare_job_for_full_processing(process_run)


def mark_job_failed(job_id, error, runtime_config=None):
    process_run = ProcessRun.objects.filter(pk=job_id).first()
    if process_run is None:
        return None
    message = str(error)
    process_run.status = ProcessRun.Status.FAILED
    process_run.error_message = message
    process_run.finished_at = timezone.now()
    process_run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
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
    supervisor = ProcessingSupervisorAgent()
    fatal_error = ""
    failed_images = 0
    ocr_calls = 0
    llm_calls = 0
    _safe_create_log(
        process_run,
        None,
        "job_started",
        runtime_config,
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
                supervisor.process_image(
                    process_run,
                    source_image,
                    runtime_config,
                    _safe_create_log,
                )
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
                    },
                    notes="Image processed successfully",
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
    prepared_job, runtime_config = prepare_job_for_full_processing(process_run)
    return process_prepared_job(prepared_job, runtime_config)
