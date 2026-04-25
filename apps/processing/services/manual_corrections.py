from __future__ import annotations

from django.db import transaction

from apps.extraction.services.validators import build_record_observations
from apps.processing.models import ExtractedDeposit, ExtractionLog, ProcessRun
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
