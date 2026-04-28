"""Servidor MCP para operar el backend Django a través de herramientas.

Expone acciones de lectura y mutación controladas para asistentes o clientes
MCP que necesitan interactuar con jobs, settings y exportaciones.
"""

from __future__ import annotations

import json
import os
from typing import Any

import django
from django.conf import settings
from mcp.server.fastmcp import FastMCP

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
django.setup()

from apps.api.services.shared_tools import upload_document_from_path
from apps.api.services.assistant_chat import AssistantChatService
from apps.api.serializers import AssistantChatSerializer
from apps.api.services.tool_dispatcher import execute_tool
from apps.processing.services.settings_service import get_or_create_processing_settings
from mcp_server.schemas import (
    AssistantChatInput,
    DepositCorrectionInput,
    JobIdInput,
    ReprocessSourceInput,
    UpdateProcessingSettingsInput,
    UploadDocumentInput,
)

mcp = FastMCP("backend-django-diplo")


def _mutations_enabled() -> bool:
    """Indica si el servidor permite operaciones de mutación."""
    return bool(getattr(settings, "MCP_ENABLE_MUTATIONS", False))


def _as_json(payload: Any) -> str:
    """Serializa la respuesta MCP con formato estable."""
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def _runtime_error_payload(error: Exception) -> str:
    """Construye un payload de error uniforme para fallos no controlados."""
    return _as_json(
        {
            "ok": False,
            "status_code": 500,
            "detail": str(error),
            "data": None,
        }
    )


def _build_assistant_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida la entrada del chat y ejecuta la misma lógica usada por la API.

    Mantener este puente evita divergencias de contrato entre consumo MCP y REST.
    """
    serializer = AssistantChatSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "ok": False,
            "status_code": 400,
            "detail": "validation_error",
            "data": serializer.errors,
        }
    service = AssistantChatService()
    response = service.answer(serializer.validated_data)
    response = service.finalize_response(
        response,
        show_debug_details=bool(
            get_or_create_processing_settings().assistant_show_debug_details
        ),
    )
    return {"ok": True, "status_code": 200, "detail": None, "data": response}


def _run_local_tool(
    tool: str, arguments: dict[str, Any] | None = None, job_id: int | None = None
) -> str:
    """Ejecuta herramientas internas y estandariza salida para clientes MCP.

    Todo resultado se envuelve en JSON con claves `ok`, `data`, `status_code`
    y `detail` para simplificar manejo en clientes aguas arriba.
    """
    try:
        payload = execute_tool(tool=tool, arguments=arguments, job_id=job_id)
        return _as_json(
            {"ok": True, "data": payload, "status_code": None, "detail": None}
        )
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool()
def health_check() -> str:
    """Comprueba el estado del backend a través de la herramienta interna."""
    return _run_local_tool("health_check")


@mcp.tool()
def upload_document(file_path: str) -> str:
    """Sube un documento DOCX local y crea una corrida de procesamiento."""
    try:
        args = UploadDocumentInput(file_path=file_path)
        payload = upload_document_from_path(args.file_path)
        return _as_json({"ok": True, "data": payload})
    except ValueError as error:
        return _as_json({"ok": False, "status_code": 400, "detail": str(error)})
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool()
def process_job(job_id: int) -> str:
    """Ejecuta OCR/LLM sobre una corrida existente.

    Requiere `MCP_ENABLE_MUTATIONS=1` para evitar mutaciones accidentales desde
    asistentes en ambientes de solo consulta.
    """
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "detail": "process_job is disabled by server configuration.",
            }
        )
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("process_job", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def reprocess_failed_sources(job_id: int) -> str:
    """Reprocesa solo las fuentes que quedaron fallidas."""
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "data": None,
                "detail": "reprocess_failed_sources is disabled by server configuration.",
            }
        )
    args = JobIdInput(job_id=job_id)
    return _run_local_tool(
        "reprocess_failed_sources",
        {"job_id": args.job_id},
        job_id=args.job_id,
    )


@mcp.tool()
def reprocess_source_image(
    job_id: int,
    source_image_id: int | None = None,
    deposit_id: int | None = None,
) -> str:
    """Reprocesa una fuente concreta o la fuente asociada a un depósito."""
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "data": None,
                "detail": "reprocess_source_image is disabled by server configuration.",
            }
        )
    args = ReprocessSourceInput(
        job_id=job_id,
        source_image_id=source_image_id,
        deposit_id=deposit_id,
    )
    payload = args.model_dump(exclude_none=True)
    return _run_local_tool(
        "reprocess_source_image",
        payload,
        job_id=args.job_id,
    )


@mcp.tool()
def get_job_status(job_id: int) -> str:
    """Obtiene el estado detallado de una corrida con relaciones anidadas."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool(
        "get_job_status", {"job_id": args.job_id}, job_id=args.job_id
    )


@mcp.tool()
def list_jobs() -> str:
    """Lista las corridas de procesamiento ordenadas por recencia."""
    return _run_local_tool("list_jobs")


@mcp.tool()
def get_job_logs(job_id: int) -> str:
    """Lista los logs de extracción de una corrida."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("get_job_logs", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def list_job_logs(job_id: int) -> str:
    """Alias legado de `get_job_logs` conservado por compatibilidad."""
    return get_job_logs(job_id)


@mcp.tool()
def export_job_excel(job_id: int) -> str:
    """Genera la exportación Excel de una corrida finalizada."""
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "detail": "export_job_excel is disabled by server configuration.",
            }
        )
    args = JobIdInput(job_id=job_id)
    return _run_local_tool(
        "export_job_excel", {"job_id": args.job_id}, job_id=args.job_id
    )


@mcp.tool()
def update_deposit_correction(
    job_id: int,
    deposit_id: int,
    referencia: str,
    valor: float,
    fecha_consignacion: str | None = None,
    hora_consignacion: str | None = None,
) -> str:
    """Corrige una consignación extraída con confirmación requerida."""
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "detail": "update_deposit_correction is disabled by server configuration.",
            }
        )
    args = DepositCorrectionInput(
        job_id=job_id,
        deposit_id=deposit_id,
        referencia=referencia,
        valor=valor,
        fecha_consignacion=fecha_consignacion,
        hora_consignacion=hora_consignacion,
    )
    return _run_local_tool(
        "update_deposit_correction",
        args.model_dump(exclude_none=True),
        job_id=args.job_id,
    )


@mcp.tool()
def get_processing_settings() -> str:
    """Obtiene la configuración de procesamiento activa."""
    return _run_local_tool("get_processing_settings")


@mcp.tool()
def get_processing_settings_options() -> str:
    """Obtiene las opciones disponibles para la configuración."""
    return _run_local_tool("get_processing_settings_options")


@mcp.tool()
def assistant_chat(
    messages: list[dict[str, str]],
    job_id: int | None = None,
    errors: int = 0,
    query_context: dict[str, Any] | None = None,
) -> str:
    """Ejecuta el flujo de chat del asistente con el mismo contrato que la API."""
    args = AssistantChatInput(
        messages=messages,
        job_id=job_id,
        errors=errors,
        query_context=query_context or {},
    )
    payload = {
        "messages": [item.model_dump() for item in args.messages],
        "errors": args.errors,
        "query_context": args.query_context,
    }
    if args.job_id is not None:
        payload["job_id"] = args.job_id
    return _as_json(_build_assistant_response(payload))


@mcp.tool()
def update_processing_settings(
    ocr_mode: str | None = None,
    ocr_provider: str | None = None,
    ocr_model: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    assistant_provider: str | None = None,
    assistant_model: str | None = None,
    assistant_api_key: str | None = None,
    assistant_show_debug_details: bool | None = None,
    assistant_temperature: float | None = None,
    assistant_num_predict: int | None = None,
    ocr_api_key: str | None = None,
    llm_api_key: str | None = None,
    request_timeout_seconds: int | None = None,
) -> str:
    """Aplica un parche parcial sobre settings de procesamiento.

    Los campos nulos se omiten para conservar semántica de PATCH.
    """
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "detail": "update_processing_settings is disabled by server configuration.",
            }
        )
    args = UpdateProcessingSettingsInput(
        ocr_mode=ocr_mode,
        ocr_provider=ocr_provider,
        ocr_model=ocr_model,
        llm_provider=llm_provider,
        llm_model=llm_model,
        assistant_provider=assistant_provider,
        assistant_model=assistant_model,
        assistant_api_key=assistant_api_key,
        assistant_show_debug_details=assistant_show_debug_details,
        assistant_temperature=assistant_temperature,
        assistant_num_predict=assistant_num_predict,
        ocr_api_key=ocr_api_key,
        llm_api_key=llm_api_key,
        request_timeout_seconds=request_timeout_seconds,
    )
    return _run_local_tool("update_processing_settings", args.to_partial_dict())


@mcp.tool()
def describe_database_schema() -> str:
    """Describe las fuentes y capacidades de consulta permitidas."""
    return _run_local_tool("describe_database_schema")


@mcp.tool()
def query_database(query: dict[str, Any]) -> str:
    """Ejecuta una consulta estructurada segura sobre fuentes permitidas."""
    return _run_local_tool("query_database", {"query": query})


@mcp.tool()
def query_database_sql(sql: str, limit: int = 100) -> str:
    """Ejecuta una consulta SQL de solo lectura cuando está permitida."""
    if not sql.strip().lower().startswith(("select", "with")):
        return _as_json(
            {
                "ok": False,
                "status_code": 400,
                "detail": "query_database_sql is read-only",
            }
        )
    return _run_local_tool("query_database_sql", {"sql": sql, "limit": limit})


@mcp.tool()
def crud_database(
    operation: str,
    source: str,
    values: dict[str, Any] | None = None,
    filters: list[dict[str, Any]] | None = None,
    limit: int = 30,
    query: dict[str, Any] | None = None,
) -> str:
    """Ejecuta operaciones CRUD estructuradas sobre fuentes permitidas."""
    if not _mutations_enabled():
        return _as_json(
            {
                "ok": False,
                "status_code": 403,
                "detail": "crud_database is disabled by server configuration.",
            }
        )
    return _run_local_tool(
        "crud_database",
        {
            "operation": operation,
            "source": source,
            "values": values or {},
            "filters": filters or [],
            "limit": limit,
            "query": query,
        },
    )


@mcp.tool()
def get_last_record_value(job_id: int | None = None) -> str:
    """Obtiene el último valor extraído de un job o del último completado."""
    arguments: dict[str, Any] = {}
    resolved_job_id: int | None = None
    if job_id is not None:
        args = JobIdInput(job_id=job_id)
        arguments["job_id"] = args.job_id
        resolved_job_id = args.job_id
    return _run_local_tool("get_last_record_value", arguments, job_id=resolved_job_id)


@mcp.tool()
def get_completed_records_summary() -> str:
    """Obtiene un resumen agregado de registros completados."""
    return _run_local_tool("get_completed_records_summary")


def main() -> None:
    """Arranca el servidor MCP sobre stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
