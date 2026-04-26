"""Servicios de corrección manual y reproceso parcial.

Permiten ajustar depósitos persistidos y volver a ejecutar solo las fuentes
necesarias sin repetir toda la corrida.
"""

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
from apps.processing.services.diagnostics import record_processing_event, stage_timer
from apps.processing.services.orchestrator import (
    is_generated_text_source,
    real_source_images_queryset,
)
from apps.processing.services.settings_service import get_runtime_config


def apply_deposit_correction(process_run: ProcessRun, item: dict) -> ProcessRun:
    """Compatibilidad de una sola corrección con la API en lote."""
    return apply_deposit_corrections(process_run, [item])


def apply_deposit_corrections(process_run: ProcessRun, items: list[dict]) -> ProcessRun:
    """Persiste correcciones manuales sobre depósitos de una corrida.

    Args:
        process_run: Corrida propietaria de los depósitos.
        items: Lista de correcciones validadas por la capa REST.

    Returns:
        Corrida recargada con relaciones actualizadas.

    Raises:
        ValueError: Si alguno de los depósitos no pertenece a la corrida.
    """
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
    return record_processing_event(
        process_run=process_run,
        source_image=source_image,
        stage=stage,
        status="failed" if kwargs.get("is_error", False) else "completed",
        runtime_config=runtime_config,
        provider=kwargs.get("provider", ""),
        model=kwargs.get("model", ""),
        raw_payload=kwargs.get("raw_payload", {}),
        raw_text=kwargs.get("raw_text", ""),
        notes=kwargs.get("notes", ""),
    )


def reprocess_source_image(
    process_run: ProcessRun, source_image: SourceImage
) -> ProcessRun:
    """Reprocesa una única imagen fuente y actualiza el estado del job."""
    if is_generated_text_source(source_image):
        raise ValueError("document_text is not a reprocessable image source.")

    runtime_config = get_runtime_config()
    supervisor = ProcessingSupervisorAgent()
    with transaction.atomic():
        source_image.deposits.all().delete()
        source_image.extraction_logs.all().delete()
        source_image.error_message = ""
        source_image.ocr_status = SourceImage.OCRStatus.PENDING
        source_image.save(update_fields=["error_message", "ocr_status", "updated_at"])

    try:
        with stage_timer(
            process_run=process_run,
            source_image=source_image,
            stage="image_reprocess",
            runtime_config=runtime_config,
        ) as event:
            records_count = supervisor.process_image(
                process_run, source_image, runtime_config, _reprocess_log_callback
            )
            event["records_count"] = records_count
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

    else:
        ExtractionLog.objects.create(
            process_run=process_run,
            source_image=source_image,
            sequence_index=source_image.sequence_index,
            stage="image_reprocessed",
            notes=f"{records_count} records reprocessed",
        )

    _update_job_after_partial_reprocess(process_run)
    return ProcessRun.objects.prefetch_related("source_images__deposits").get(
        pk=process_run.pk
    )


def reprocess_failed_sources(process_run: ProcessRun) -> ProcessRun:
    """Reprocesa todas las fuentes que terminaron con error."""
    failed_sources = list(
        real_source_images_queryset(process_run)
        .filter(ocr_status=SourceImage.OCRStatus.FAILED)
        .order_by("sequence_index", "id")
    )
    if not failed_sources:
        return ProcessRun.objects.prefetch_related("source_images__deposits").get(
            pk=process_run.pk
        )

    for source_image in failed_sources:
        reprocess_source_image(process_run, source_image)

    return ProcessRun.objects.prefetch_related("source_images__deposits").get(
        pk=process_run.pk
    )


def _update_job_after_partial_reprocess(process_run: ProcessRun) -> None:
    """Recalcula contadores y estado de la corrida luego de un reproceso parcial."""
    process_run.refresh_from_db()
    total_images = real_source_images_queryset(process_run).count()
    failed_images = (
        real_source_images_queryset(process_run)
        .filter(ocr_status=SourceImage.OCRStatus.FAILED)
        .count()
    )
    total_records = process_run.deposits.count()
    process_run.total_images = total_images
    process_run.total_records = total_records
    if failed_images == 0:
        process_run.status = ProcessRun.Status.COMPLETED
        process_run.error_message = ""
    elif total_records > 0 or failed_images < total_images:
        process_run.status = ProcessRun.Status.COMPLETED_WITH_ERRORS
        first_failed = (
            real_source_images_queryset(process_run)
            .filter(ocr_status=SourceImage.OCRStatus.FAILED)
            .order_by("sequence_index", "id")
            .first()
        )
        process_run.error_message = first_failed.error_message if first_failed else ""
    else:
        process_run.status = ProcessRun.Status.FAILED
        first_failed = (
            real_source_images_queryset(process_run)
            .filter(ocr_status=SourceImage.OCRStatus.FAILED)
            .order_by("sequence_index", "id")
            .first()
        )
        process_run.error_message = first_failed.error_message if first_failed else ""
    process_run.save(
        update_fields=[
            "status",
            "error_message",
            "total_images",
            "total_records",
            "updated_at",
        ]
    )
