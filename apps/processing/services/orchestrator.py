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


def prepare_job_for_processing(process_run):
    runtime_config = get_runtime_config()
    process_run = ProcessRun.objects.get(pk=process_run.pk)
    with transaction.atomic():
        process_run.deposits.all().delete()
        process_run.extraction_logs.all().delete()
        process_run.status = ProcessRun.Status.PROCESSING
        process_run.started_at = timezone.now()
        process_run.finished_at = None
        process_run.error_message = ""
        process_run.total_records = 0
        process_run.provider_config_snapshot = as_snapshot_dict(runtime_config)
        process_run.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "error_message",
                "total_records",
                "provider_config_snapshot",
                "updated_at",
            ]
        )
        process_run.source_images.update(
            ocr_status=SourceImage.OCRStatus.PENDING,
            ocr_raw_text="",
            error_message="",
            ocr_provider=runtime_config.ocr_provider,
        )
    return process_run, runtime_config


def process_prepared_job(process_run, runtime_config):
    supervisor = ProcessingSupervisorAgent()
    total_records = 0
    fatal_error = ""
    failed_images = 0
    _safe_create_log(
        process_run,
        None,
        "job_started",
        runtime_config,
        notes="Supervisor multi-agent processing started",
    )
    final_status = ProcessRun.Status.FAILED
    try:
        # Process extracted text from the Word document first
        if process_run.extracted_text.strip():
            try:
                total_records += supervisor.process_text(
                    process_run,
                    process_run.extracted_text,
                    runtime_config,
                    _safe_create_log,
                )
            except Exception as error:
                _safe_create_log(
                    process_run,
                    None,
                    "text_processing_failed",
                    runtime_config,
                    notes=str(error),
                    is_error=True,
                )
                if not fatal_error:
                    fatal_error = str(error)
        
        for source_image in process_run.source_images.order_by("sequence_index", "id"):
            try:
                total_records += supervisor.process_image(
                    process_run,
                    source_image,
                    runtime_config,
                    _safe_create_log,
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
                    notes=str(error),
                    is_error=True,
                )
                if not fatal_error:
                    fatal_error = str(error)
        final_status = ProcessRun.Status.COMPLETED
        if failed_images > 0:
            final_status = ProcessRun.Status.COMPLETED_WITH_ERRORS
        if failed_images == process_run.total_images:
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
        process_run.total_records = total_records
        process_run.finished_at = timezone.now()
        process_run.status = final_status
        process_run.error_message = fatal_error
        process_run.save(
            update_fields=[
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
            notes=f"status={process_run.status}",
            is_error=process_run.status == ProcessRun.Status.FAILED,
        )
    return process_run


def process_job(process_run):
    prepared_job, runtime_config = prepare_job_for_processing(process_run)
    return process_prepared_job(prepared_job, runtime_config)
