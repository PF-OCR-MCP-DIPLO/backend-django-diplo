from django.db import transaction
from django.utils import timezone

from apps.extraction.services.image_validation import validate_source_image
from apps.extraction.services.ocr_service import extract_raw_text
from apps.extraction.services.structuring_service import extract_structured_data
from apps.extraction.services.validators import build_record_observations
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    SourceImage,
)
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


def process_job(process_run):
    runtime_config = get_runtime_config()
    process_run = ProcessRun.objects.prefetch_related("source_images").get(
        pk=process_run.pk
    )
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
    total_records = 0
    fatal_error = ""
    failed_images = 0
    _create_log(
        process_run,
        None,
        "job_started",
        runtime_config,
        notes="Sequential processing started",
    )
    try:
        for source_image in process_run.source_images.order_by("sequence_index", "id"):
            try:
                validate_source_image(source_image)
                ocr_result = extract_raw_text(source_image, runtime_config)
                source_image.ocr_raw_text = ocr_result["text"]
                source_image.ocr_provider = ocr_result["provider"]
                _create_log(
                    process_run,
                    source_image,
                    "ocr_extracted",
                    runtime_config,
                    provider=ocr_result["provider"],
                    model=ocr_result["model"],
                    raw_payload=ocr_result["payload"],
                    raw_text=ocr_result["text"],
                    notes=f"OCR mode resolved to {ocr_result['mode']}",
                )
                structured_result = extract_structured_data(
                    source_image, ocr_result["text"], runtime_config
                )
                _create_log(
                    process_run,
                    source_image,
                    "llm_structured",
                    runtime_config,
                    provider=structured_result["provider"],
                    model=structured_result["model"],
                    raw_payload={"records_count": len(structured_result["records"])},
                )
                for structured_record in structured_result["records"]:
                    observations, is_current_month = build_record_observations(
                        structured_record.get("fecha_consignacion")
                    )
                    ExtractedDeposit.objects.create(
                        process_run=process_run,
                        source_image=source_image,
                        sequence_index=source_image.sequence_index,
                        fecha_consignacion=structured_record.get("fecha_consignacion")
                        or "",
                        hora_consignacion=structured_record.get("hora_consignacion")
                        or "",
                        referencia=structured_record["referencia"],
                        valor=structured_record["valor"],
                        is_current_month=is_current_month,
                        observations=observations,
                        structured_payload=structured_record,
                    )
                    total_records += 1
                source_image.ocr_status = SourceImage.OCRStatus.PROCESSED
                source_image.error_message = ""
                source_image.save(
                    update_fields=[
                        "ocr_status",
                        "ocr_raw_text",
                        "ocr_provider",
                        "error_message",
                        "updated_at",
                    ]
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
                _create_log(
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
        process_run.status = ProcessRun.Status.COMPLETED
        if failed_images > 0:
            process_run.status = ProcessRun.Status.COMPLETED_WITH_ERRORS
        if failed_images == process_run.total_images:
            process_run.status = ProcessRun.Status.FAILED
    except Exception as error:
        process_run.status = ProcessRun.Status.FAILED
        fatal_error = str(error)
        _create_log(
            process_run,
            None,
            "job_failed",
            runtime_config,
            notes=fatal_error,
            is_error=True,
        )
    process_run.total_records = total_records
    process_run.finished_at = timezone.now()
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
    _create_log(
        process_run,
        None,
        "job_finished",
        runtime_config,
        notes=f"status={process_run.status}",
        is_error=process_run.status == ProcessRun.Status.FAILED,
    )
    return process_run
