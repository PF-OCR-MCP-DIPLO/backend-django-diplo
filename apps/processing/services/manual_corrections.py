from __future__ import annotations

from django.db import transaction

from apps.extraction.services.validators import build_record_observations
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    SourceImage,
)
from apps.processing.services.agents import ProcessingSupervisorAgent
from apps.processing.services.settings_service import get_runtime_config


def apply_deposit_correction(process_run: ProcessRun, item: dict) -> ProcessRun:
    return apply_deposit_corrections(process_run, [item])


def apply_deposit_corrections(process_run: ProcessRun, items: list[dict]) -> ProcessRun:
    runtime_config = get_runtime_config()
    deposits = {
        deposit.id: deposit
        for deposit in process_run.deposits.select_related("source_image").all()
    }

    missing_ids = sorted(
        str(item["id"]) for item in items if item["id"] not in deposits
    )
    if missing_ids:
        raise ValueError(
            "One or more deposits do not belong to this job.",
            {"deposit_ids": missing_ids},
        )

    with transaction.atomic():
        for item in items:
            deposit = deposits[item["id"]]
            observations, is_current_month = build_record_observations(
                item["fecha_consignacion"],
                item,
                runtime_config.extraction_criteria,
            )
            deposit.fecha_consignacion = item["fecha_consignacion"]
            deposit.hora_consignacion = item["hora_consignacion"]
            deposit.referencia = item["referencia"]
            deposit.valor = item["valor"]
            deposit.is_current_month = is_current_month
            deposit.observations = observations
            deposit.structured_payload = {
                **deposit.structured_payload,
                "fecha_consignacion": deposit.fecha_consignacion,
                "hora_consignacion": deposit.hora_consignacion,
                "referencia": deposit.referencia,
                "valor": float(deposit.valor),
                "archivo_origen": deposit.source_image.source_name,
                "manually_corrected": True,
            }
            deposit.save(
                update_fields=[
                    "fecha_consignacion",
                    "hora_consignacion",
                    "referencia",
                    "valor",
                    "is_current_month",
                    "observations",
                    "structured_payload",
                ]
            )

        ExtractionLog.objects.create(
            process_run=process_run,
            sequence_index=0,
            stage="manual_corrections_saved",
            notes=f"{len(items)} corrected rows persisted",
        )

    return ProcessRun.objects.prefetch_related("source_images__deposits").get(
        pk=process_run.pk
    )


def _reprocess_log_callback(process_run, source_image, stage, runtime_config, **kwargs):
    return ExtractionLog.objects.create(
        process_run=process_run,
        source_image=source_image,
        sequence_index=(
            getattr(source_image, "sequence_index", 0) if source_image else 0
        ),
        stage=stage,
        ocr_mode=runtime_config.ocr_mode,
        provider=kwargs.get("provider", ""),
        model=kwargs.get("model", ""),
        raw_payload=kwargs.get("raw_payload", {}),
        raw_text=kwargs.get("raw_text", ""),
        notes=kwargs.get("notes", ""),
        is_error=kwargs.get("is_error", False),
    )


def reprocess_source_image(
    process_run: ProcessRun, source_image: SourceImage
) -> ProcessRun:
    runtime_config = get_runtime_config()
    supervisor = ProcessingSupervisorAgent()
    with transaction.atomic():
        source_image.deposits.all().delete()
        source_image.error_message = ""
        source_image.ocr_status = SourceImage.OCRStatus.PENDING
        source_image.save(update_fields=["error_message", "ocr_status", "updated_at"])

    try:
        records_count = supervisor.process_image(
            process_run, source_image, runtime_config, _reprocess_log_callback
        )
    except Exception as error:
        source_image.ocr_status = SourceImage.OCRStatus.FAILED
        source_image.error_message = str(error)
        source_image.save(update_fields=["ocr_status", "error_message", "updated_at"])
        ExtractionLog.objects.create(
            process_run=process_run,
            source_image=source_image,
            sequence_index=source_image.sequence_index,
            stage="image_reprocess_failed",
            notes=str(error),
            is_error=True,
        )
        raise

    process_run.total_records = process_run.deposits.count()
    process_run.save(update_fields=["total_records", "updated_at"])
    ExtractionLog.objects.create(
        process_run=process_run,
        source_image=source_image,
        sequence_index=source_image.sequence_index,
        stage="image_reprocessed",
        notes=f"{records_count} records reprocessed",
    )
    return ProcessRun.objects.prefetch_related("source_images__deposits").get(
        pk=process_run.pk
    )
