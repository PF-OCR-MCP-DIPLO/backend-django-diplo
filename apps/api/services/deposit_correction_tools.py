from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.api.serializers import DepositCorrectionSerializer
from apps.api.services.pending_actions import pending_action_label
from apps.processing.models import ExtractedDeposit, ProcessRun
from apps.processing.services.manual_corrections import apply_deposit_correction

_ALLOWED_UPDATE_FIELDS = {
    "fecha_consignacion",
    "hora_consignacion",
    "referencia",
    "valor",
}


def extract_deposit_correction_deposit_id(
    text: str, query_context: dict[str, Any] | None = None
) -> int | None:
    context = query_context or {}
    for key in ("depositId", "deposit_id", "depositID", "resultId", "rowId"):
        value = context.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    import re

    match = re.search(r"(?:deposito|depósito|deposit|fila|registro)\s*#?\s*(\d+)", text)
    if match is not None:
        return int(match.group(1))
    match = re.search(r"(?:id\s*#?|id:)\s*(\d+)", text)
    if match is not None:
        return int(match.group(1))
    return None


def normalize_deposit_correction_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    serializer = DepositCorrectionSerializer(data=arguments)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def deposit_correction_missing_fields(
    arguments: dict[str, Any], job_id: int | None
) -> list[str]:
    missing: list[str] = []
    if job_id is None and not str(arguments.get("job_id") or "").strip().isdigit():
        missing.append("job_id")
    if not str(arguments.get("deposit_id") or "").strip().isdigit():
        missing.append("deposit_id")
    return missing


def deposit_correction_needs_clarification(
    arguments: dict[str, Any], job_id: int | None
) -> str | None:
    missing = deposit_correction_missing_fields(arguments, job_id)
    if missing:
        return (
            "Para corregir la fila necesito que me indiques " + ", ".join(missing) + "."
        )

    candidate_values = arguments.get("values")
    if not isinstance(candidate_values, dict):
        candidate_values = arguments
    if not any(field in candidate_values for field in _ALLOWED_UPDATE_FIELDS):
        return "Para corregir la fila necesito al menos un campo a actualizar."
    return None


def deposit_correction_summary(arguments: dict[str, Any]) -> str:
    deposit_id = arguments.get("deposit_id") or arguments.get("id") or "N/D"
    values = (
        arguments.get("values")
        if isinstance(arguments.get("values"), dict)
        else arguments
    )
    parts: list[str] = []
    if "referencia" in values:
        parts.append(f"referencia a {values['referencia']}")
    if "valor" in values:
        parts.append(f"valor a {values['valor']}")
    if "fecha_consignacion" in values:
        parts.append(f"fecha a {values['fecha_consignacion']}")
    if "hora_consignacion" in values:
        parts.append(f"hora a {values['hora_consignacion']}")
    detail = ", ".join(parts) if parts else "campos actualizados"
    return f"Actualizar la consignación #{deposit_id}: {detail}"


def deposit_correction_confirmation_message(arguments: dict[str, Any]) -> str:
    deposit_id = arguments.get("deposit_id") or arguments.get("id")
    base = "Necesito tu confirmacion para corregir esta fila de consignacion."
    if deposit_id is not None:
        return f"{base} Fila #{deposit_id}."
    return base


def deposit_correction_success_message(payload: dict[str, Any]) -> str:
    return f"Corrigí la fila #{payload.get('deposit_id')} del job #{payload.get('job_id')}."


def pending_action_label_for_deposit_correction() -> str:
    return pending_action_label("update_deposit_correction")


def deposit_correction_values_from_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    values = arguments.get("values")
    if isinstance(values, dict) and values:
        return values
    return {
        field: arguments[field]
        for field in _ALLOWED_UPDATE_FIELDS
        if field in arguments
    }


def deposit_correction_has_updates(arguments: dict[str, Any]) -> bool:
    return bool(deposit_correction_values_from_arguments(arguments))


def deposit_correction_payload_for_correction(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(arguments)
    normalized["values"] = deposit_correction_values_from_arguments(arguments)
    return normalized


def deposit_correction_success_description(payload: dict[str, Any]) -> str:
    deposit_id = payload.get("deposit_id", "N/D")
    job_id = payload.get("job_id", "N/D")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    description = []
    for field in ("referencia", "valor", "fecha_consignacion", "hora_consignacion"):
        if field in data:
            description.append(f"{field}={data[field]}")
    suffix = f" ({', '.join(description)})" if description else ""
    return f"Corrigí la fila #{deposit_id} del job #{job_id}{suffix}."


def execute_deposit_correction(arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        return {"detail": "update_deposit_correction requiere arguments como objeto."}

    serializer = DepositCorrectionSerializer(data=arguments)
    serializer.is_valid(raise_exception=True)
    job_id = serializer.validated_data["job_id"]
    deposit_id = serializer.validated_data["id"]

    job = ProcessRun.objects.filter(pk=job_id).first()
    if job is None:
        return {"detail": "job_id invalido."}
    if job.status == ProcessRun.Status.PROCESSING:
        return {"detail": "El job no se puede editar mientras esta procesando."}

    try:
        deposit = job.deposits.select_related("source_image").get(pk=deposit_id)
    except ExtractedDeposit.DoesNotExist:
        return {"detail": "deposit_id no pertenece al job indicado."}

    item = {
        "id": deposit.id,
        "fecha_consignacion": serializer.validated_data["fecha_consignacion"]
        or deposit.fecha_consignacion,
        "hora_consignacion": serializer.validated_data["hora_consignacion"]
        or deposit.hora_consignacion,
        "referencia": serializer.validated_data["referencia"],
        "valor": serializer.validated_data["valor"],
    }
    updated_job = apply_deposit_correction(job, item)
    updated_deposit = updated_job.deposits.get(pk=deposit.id)
    return {
        "job_id": updated_job.id,
        "deposit_id": updated_deposit.id,
        "operation": "update",
        "data": {
            "fecha_consignacion": updated_deposit.fecha_consignacion,
            "hora_consignacion": updated_deposit.hora_consignacion,
            "referencia": updated_deposit.referencia,
            "valor": str(updated_deposit.valor),
        },
    }
