"""Resolución de tareas y contexto para el asistente.

Convierte mensajes del usuario, contexto del job y herramientas invocadas en
una tarea de alto nivel que el agente puede ejecutar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from apps.processing.models import ProcessRun
from apps.processing.services.extraction_criteria import normalize_extraction_criteria
from apps.processing.services.settings_service import get_or_create_processing_settings

AssistantTaskName = Literal[
    "explain_job_summary",
    "explain_job_findings",
    "explain_row_issue",
    "suggest_row_correction",
    "summarize_extraction_logs",
    "explain_extraction_criteria",
    "prepare_export",
    "prepare_reprocess",
    "answer_general_question",
]


@dataclass(frozen=True)
class AssistantTask:
    name: AssistantTaskName
    summary: str
    requires_confirmation: bool = False


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def resolve_assistant_task(
    *,
    user_message: str,
    job_id: int | None,
    query_context: dict[str, Any] | None,
    tool: str,
) -> AssistantTask:
    """Determina la tarea conversacional a partir del mensaje y el contexto."""
    text = _normalize_text(user_message)
    context = query_context or {}
    has_row_context = any(
        key in context
        for key in ("resultId", "rowId", "depositId", "sourceImageId", "selectedRowId")
    )
    has_ocr_context = any(
        key in context
        for key in (
            "sourceImageId",
            "currentImageId",
            "selectedField",
            "visibleIssueIds",
        )
    )

    if (
        has_row_context
        or has_ocr_context
        or any(term in text for term in ("fila", "row", "registro", "celda"))
    ):
        if any(
            term in text
            for term in ("corrige", "corregir", "corrección", "correccion", "suger")
        ):
            return AssistantTask("suggest_row_correction", "Sugerir corrección de fila")
        return AssistantTask("explain_row_issue", "Explicar problema de una fila")

    if tool == "get_job_logs" or any(
        term in text for term in ("log", "ocr", "error", "fallo", "resultado")
    ):
        return AssistantTask("summarize_extraction_logs", "Resumir logs del job")

    if tool == "get_processing_settings" or any(
        term in text
        for term in (
            "criterios",
            "validación",
            "validacion",
            "settings",
            "configuracion",
            "configuración",
        )
    ):
        return AssistantTask(
            "explain_extraction_criteria", "Explicar criterios y settings"
        )

    if tool == "get_job_status" or any(
        term in text
        for term in (
            "resumen",
            "estado del job",
            "estado de este job",
            "cómo va",
            "como va",
            "job actual",
        )
    ):
        return AssistantTask("explain_job_summary", "Explicar resumen del job")

    if any(term in text for term in ("hallazgo", "error", "errores", "issue")):
        return AssistantTask("explain_job_findings", "Explicar hallazgos del job")

    if any(term in text for term in ("exportar", "excel", "export")):
        return AssistantTask(
            "prepare_export",
            "Preparar exportación",
            requires_confirmation=True,
        )

    if any(
        term in text
        for term in ("reprocesar", "procesar de nuevo", "volver a procesar", "procesar")
    ):
        return AssistantTask(
            "prepare_reprocess",
            "Preparar reprocesamiento",
            requires_confirmation=True,
        )

    return AssistantTask("answer_general_question", "Responder conversación general")


def _summarize_deposit(deposit: Any) -> dict[str, Any]:
    observations = (
        list(deposit.observations or []) if hasattr(deposit, "observations") else []
    )
    return {
        "id": getattr(deposit, "id", None),
        "sequence_index": getattr(deposit, "sequence_index", None),
        "referencia": getattr(deposit, "referencia", ""),
        "valor": str(getattr(deposit, "valor", "")),
        "fecha_consignacion": getattr(deposit, "fecha_consignacion", ""),
        "hora_consignacion": getattr(deposit, "hora_consignacion", ""),
        "observations": observations[:3],
    }


def build_assistant_task_context(
    *,
    task: AssistantTask,
    job_id: int | None,
    query_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Construye el contexto enriquecido que usará el agente del asistente."""
    context = query_context or {}
    task_context: dict[str, Any] = {
        "task": task.name,
        "job_id": job_id,
    }

    if job_id is None:
        return task_context

    job = (
        ProcessRun.objects.prefetch_related("source_images__deposits")
        .filter(pk=job_id)
        .first()
    )
    if job is None:
        task_context["job_found"] = False
        return task_context

    settings_obj = get_or_create_processing_settings()
    deposits = list(job.deposits.order_by("sequence_index", "id"))
    issue_rows = [
        deposit for deposit in deposits if getattr(deposit, "observations", None)
    ]
    selected_ids = {
        context.get("resultId"),
        context.get("rowId"),
        context.get("depositId"),
    }
    selected_id = next(
        (
            int(value)
            for value in selected_ids
            if isinstance(value, int)
            or (isinstance(value, str) and str(value).isdigit())
        ),
        None,
    )
    selected_row = None
    if selected_id is not None:
        selected_row = next(
            (deposit for deposit in deposits if deposit.id == selected_id), None
        )

    task_context.update(
        {
            "job_found": True,
            "job": {
                "id": job.id,
                "filename": job.original_filename,
                "status": job.status,
                "total_images": job.total_images,
                "total_records": job.total_records,
            },
            "findings": {
                "rows_with_observations": len(issue_rows),
                "sample": [_summarize_deposit(deposit) for deposit in issue_rows[:3]],
            },
            "criteria": {
                "enabled_fields": [
                    field.get("key")
                    for field in normalize_extraction_criteria(
                        settings_obj.extraction_criteria
                    ).get("fields", [])
                    if field.get("enabled")
                ],
            },
        }
    )

    if selected_row is not None:
        task_context["selected_row"] = _summarize_deposit(selected_row)

    if task.name == "summarize_extraction_logs":
        logs = list(job.extraction_logs.order_by("sequence_index", "id")[:8])
        task_context["logs"] = [
            {
                "stage": getattr(log, "stage", ""),
                "provider": getattr(log, "provider", ""),
                "model": getattr(log, "model", ""),
                "is_error": getattr(log, "is_error", False),
                "notes": getattr(log, "notes", "")[:120],
            }
            for log in logs
        ]

    return task_context
