from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.extraction.services.ocr_service import extract_raw_text
from apps.extraction.services.image_validation import validate_source_image
from apps.extraction.services.structuring_service import extract_structured_data
from apps.extraction.services.validators import build_record_observations
from apps.processing.models import ExtractedDeposit, ProcessRun, SourceImage


def process_job(process_run):
    process_run = ProcessRun.objects.prefetch_related("source_images").get(
        pk=process_run.pk
    )
    with transaction.atomic():
        process_run.deposits.all().delete()
        process_run.status = ProcessRun.Status.PROCESSING
        process_run.started_at = timezone.now()
        process_run.finished_at = None
        process_run.error_message = ""
        process_run.total_records = 0
        process_run.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "error_message",
                "total_records",
                "updated_at",
            ]
        )
        process_run.source_images.update(
            ocr_status=SourceImage.OCRStatus.PENDING,
            ocr_raw_text="",
            error_message="",
            ocr_provider=settings.OCR_PROVIDER,
        )
    total_records = 0
    fatal_error = ""
    try:
        for source_image in process_run.source_images.order_by("sequence_index", "id"):
            try:
                validate_source_image(source_image)
                raw_text = extract_raw_text(source_image)
                source_image.ocr_raw_text = raw_text
                structured_records = extract_structured_data(source_image, raw_text)
                for structured_record in structured_records:
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
                if not fatal_error:
                    fatal_error = str(error)
        process_run.status = ProcessRun.Status.COMPLETED
        if (
            process_run.source_images.filter(
                ocr_status=SourceImage.OCRStatus.FAILED
            ).count()
            == process_run.total_images
        ):
            process_run.status = ProcessRun.Status.FAILED
    except Exception as error:
        process_run.status = ProcessRun.Status.FAILED
        fatal_error = str(error)
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
    return process_run
