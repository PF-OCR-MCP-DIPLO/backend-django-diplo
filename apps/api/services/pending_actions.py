from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from apps.api.services.tool_risk import get_tool_risk_level

ALLOWED_PENDING_ACTION_TOOLS = {
    "crud_database",
    "process_job",
    "export_job_excel",
    "update_processing_settings",
    "update_deposit_correction",
}

PENDING_ACTION_REQUIRED_FIELDS: dict[str, set[str]] = {
    "update_deposit_correction": {"job_id", "deposit_id"},
}


def pending_action_label(tool: str) -> str:
    labels = {
        "update_deposit_correction": "Corregir consignación",
        "process_job": "Procesar job",
        "export_job_excel": "Exportar Excel",
        "update_processing_settings": "Actualizar configuración",
        "crud_database": "Modificar base de datos",
    }
    return labels.get(tool, "Acción pendiente")


def pending_action_id(payload: dict[str, Any]) -> str:
    raw_identity = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:16]


def normalize_pending_action(
    pending_action: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    tool = str(pending_action.get("tool") or "").strip()
    if tool not in ALLOWED_PENDING_ACTION_TOOLS:
        return pending_action, "La acción pendiente es inválida."

    arguments = pending_action.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    normalized = dict(pending_action)
    normalized["tool"] = tool
    normalized["arguments"] = arguments
    normalized["label"] = str(pending_action.get("label") or pending_action_label(tool))
    normalized["summary"] = str(pending_action.get("summary") or "")
    normalized["risk"] = str(pending_action.get("risk") or get_tool_risk_level(tool))

    if "id" not in normalized or not str(normalized["id"]).strip():
        normalized["id"] = pending_action_id(
            {
                "tool": tool,
                "arguments": arguments,
                "job_id": pending_action.get("job_id"),
                "intent_name": pending_action.get("intent_name"),
            }
        )

    return normalized, None


def build_pending_action(
    *,
    tool: str,
    arguments: dict[str, Any],
    intent_name: str,
    intent_summary: str,
    job_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool,
        "label": pending_action_label(tool),
        "summary": intent_summary,
        "risk": get_tool_risk_level(tool),
        "arguments": arguments,
        "intent_name": intent_name,
        "intent_summary": intent_summary,
    }
    if job_id is not None:
        payload["job_id"] = job_id
    payload["id"] = pending_action_id(
        {
            "tool": tool,
            "arguments": arguments,
            "job_id": job_id,
            "intent_name": intent_name,
        }
    )
    return payload


def pending_action_requires_clarification(
    tool: str, arguments: dict[str, Any] | None, job_id: int | None
) -> str | None:
    if tool not in PENDING_ACTION_REQUIRED_FIELDS:
        return None

    arguments = arguments or {}
    required = PENDING_ACTION_REQUIRED_FIELDS[tool]
    missing = sorted(
        field
        for field in required
        if not isinstance(arguments.get(field), int)
        and not str(arguments.get(field) or "").strip().isdigit()
    )
    if job_id is None and not str(arguments.get("job_id") or "").strip().isdigit():
        missing.append("job_id")

    if missing:
        return (
            "Para corregir la fila necesito que me indiques " + ", ".join(missing) + "."
        )

    values = arguments.get("values")
    candidate_values = values if isinstance(values, dict) else arguments
    allowed = {"fecha_consignacion", "hora_consignacion", "referencia", "valor"}
    if not any(key in candidate_values for key in allowed):
        return "Para corregir la fila necesito al menos un campo a actualizar."

    return None


def validate_pending_action(
    pending_action: dict[str, Any], job_id: int | None
) -> str | None:
    tool = str(pending_action.get("tool") or "").strip()
    if tool not in ALLOWED_PENDING_ACTION_TOOLS:
        return "La acción pendiente ya no es válida."
    if get_tool_risk_level(tool) == "restricted":
        return "La acción pendiente ya no puede ejecutarse."

    arguments = pending_action.get("arguments")
    if not isinstance(arguments, dict):
        return "La acción pendiente está incompleta."

    if tool == "update_deposit_correction":
        resolved_job_id = job_id or arguments.get("job_id")
        deposit_id = arguments.get("deposit_id")
        if not str(resolved_job_id or "").strip().isdigit():
            return "La acción pendiente está incompleta."
        if not str(deposit_id or "").strip().isdigit():
            return "La acción pendiente está incompleta."
        values = arguments.get("values")
        candidate_values = values if isinstance(values, dict) else arguments
        if not any(
            key in candidate_values
            for key in (
                "fecha_consignacion",
                "hora_consignacion",
                "referencia",
                "valor",
            )
        ):
            return "La acción pendiente está incompleta."

    return None


def clear_pending_action(query_context: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(query_context)
    cleaned.pop("pending_action", None)
    return cleaned


def confirmation_message(tool: str, arguments: dict[str, Any]) -> str:
    messages = {
        "crud_database": "Necesito tu confirmacion para ejecutar cambios en la base de datos.",
        "update_processing_settings": "Necesito tu confirmacion para actualizar la configuracion.",
        "process_job": "Necesito tu confirmacion para iniciar el procesamiento de este job.",
        "export_job_excel": "Necesito tu confirmacion para exportar este job a Excel.",
        "upload_document": "Necesito tu confirmacion para subir este documento.",
        "update_deposit_correction": "Necesito tu confirmacion para corregir esta fila de consignacion.",
    }
    detail = messages.get(tool, "Necesito tu confirmacion para ejecutar esta accion.")
    if tool == "process_job" and "job_id" in arguments:
        return f"{detail} Job #{arguments.get('job_id')}."
    if tool == "update_deposit_correction" and "deposit_id" in arguments:
        return f"{detail} Fila #{arguments.get('deposit_id')}."
    return detail


@dataclass(frozen=True)
class PendingActionContract:
    id: str
    tool: str
    label: str
    summary: str
    risk: str
    arguments: dict[str, Any]
