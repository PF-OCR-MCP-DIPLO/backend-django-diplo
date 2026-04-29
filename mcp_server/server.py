"""Servidor MCP para operar el backend Django a través de herramientas.

Expone acciones de lectura y mutación controladas para asistentes o clientes
MCP que necesitan interactuar con jobs, settings y exportaciones.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import django
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError as DrfValidationError

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
django.setup()

from apps.api.serializers import AssistantChatSerializer
from apps.api.services.assistant_chat import AssistantChatService
from apps.api.services.shared_tools import upload_document_from_path
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

logger = logging.getLogger(__name__)

READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
MUTATION_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
DESTRUCTIVE_MUTATION_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)
RESTRICTED_READ_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "secret", "token", "password")

mcp = FastMCP(
    "backend-django-diplo",
    instructions=(
        "Servidor MCP didactico para consultar y operar jobs de procesamiento "
        "DOCX/OCR/LLM. Las mutaciones requieren MCP_ENABLE_MUTATIONS=1."
    ),
)


def _mutations_enabled() -> bool:
    """Indica si el servidor permite operaciones de mutación."""
    return bool(getattr(settings, "MCP_ENABLE_MUTATIONS", False))


def _as_json(payload: Any) -> str:
    """Serializa la respuesta MCP con formato estable."""
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def _sanitize_for_mcp(value: Any) -> Any:
    """Evita exponer secretos en respuestas MCP, incluso ante bugs aguas abajo."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text.startswith("has_") or key_text == "requires_api_key":
                sanitized[key] = _sanitize_for_mcp(item)
            elif any(part in key_text for part in SENSITIVE_KEY_PARTS):
                sanitized[key] = "***"
            else:
                sanitized[key] = _sanitize_for_mcp(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_mcp(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_mcp(item) for item in value]
    return value


def _success_envelope(
    data: Any,
    *,
    status_code: int | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Construye el sobre JSON estable para resultados exitosos."""
    return {
        "ok": True,
        "status_code": status_code,
        "detail": detail,
        "data": _sanitize_for_mcp(data),
    }


def _error_envelope(
    status_code: int,
    detail: str,
    *,
    data: Any = None,
    code: str | None = None,
) -> dict[str, Any]:
    """Construye el sobre JSON estable para errores controlados."""
    payload = {
        "ok": False,
        "status_code": status_code,
        "detail": detail,
        "data": _sanitize_for_mcp(data),
    }
    if code:
        payload["code"] = code
    return payload


def _pydantic_error_data(error: PydanticValidationError) -> list[dict[str, Any]]:
    """Convierte errores Pydantic sin incluir valores de entrada sensibles."""
    cleaned: list[dict[str, Any]] = []
    for item in error.errors():
        cleaned.append({key: value for key, value in item.items() if key != "input"})
    return cleaned


def _validation_error_payload(error: PydanticValidationError) -> str:
    """Respuesta MCP controlada para errores de schema de entrada."""
    return _as_json(
        _error_envelope(
            400,
            "validation_error",
            data=_pydantic_error_data(error),
            code="validation_error",
        )
    )


def _drf_validation_error_payload(error: DrfValidationError) -> str:
    """Respuesta MCP controlada para validaciones de serializers DRF."""
    return _as_json(
        _error_envelope(
            400,
            "validation_error",
            data=getattr(error, "detail", None),
            code="validation_error",
        )
    )


def _mutation_disabled_payload(tool: str) -> str:
    """Respuesta uniforme para mutaciones deshabilitadas por configuración."""
    return _as_json(
        _error_envelope(
            403,
            f"{tool} is disabled by server configuration.",
            code="mutation_disabled",
        )
    )


def _runtime_error_payload(error: Exception) -> str:
    """Construye un payload de error uniforme para fallos no controlados."""
    logger.exception("Unhandled MCP tool error: %s", error.__class__.__name__)
    return _as_json(_error_envelope(500, "internal_error", code="internal_error"))


def _controlled_exception_payload(error: Exception) -> str:
    """Convierte excepciones esperables en errores MCP accionables."""
    if isinstance(error, PydanticValidationError):
        return _validation_error_payload(error)
    if isinstance(error, DrfValidationError):
        return _drf_validation_error_payload(error)
    if isinstance(error, ObjectDoesNotExist):
        return _as_json(
            _error_envelope(404, "not_found", data=str(error), code="not_found")
        )
    if isinstance(error, ValueError):
        return _as_json(_error_envelope(400, str(error), code="invalid_request"))
    return _runtime_error_payload(error)


def _json_response_for_local_tool(
    tool: str,
    arguments: dict[str, Any] | None = None,
    job_id: int | None = None,
) -> str:
    payload = execute_tool(tool=tool, arguments=arguments, job_id=job_id)
    return _as_json(_success_envelope(payload))


def _build_assistant_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida la entrada del chat y ejecuta la misma lógica usada por la API.

    Mantener este puente evita divergencias de contrato entre consumo MCP y REST.
    """
    serializer = AssistantChatSerializer(data=payload)
    if not serializer.is_valid():
        return _error_envelope(
            400,
            "validation_error",
            data=serializer.errors,
            code="validation_error",
        )
    service = AssistantChatService()
    response = service.answer(serializer.validated_data)
    response = service.finalize_response(
        response,
        show_debug_details=bool(
            get_or_create_processing_settings().assistant_show_debug_details
        ),
    )
    return _success_envelope(response, status_code=200)


def _run_local_tool(
    tool: str, arguments: dict[str, Any] | None = None, job_id: int | None = None
) -> str:
    """Ejecuta herramientas internas y estandariza salida para clientes MCP.

    Todo resultado se envuelve en JSON con claves `ok`, `data`, `status_code`
    y `detail` para simplificar manejo en clientes aguas arriba.
    """
    try:
        return _json_response_for_local_tool(tool, arguments, job_id)
    except (
        PydanticValidationError,
        DrfValidationError,
        ObjectDoesNotExist,
        ValueError,
    ) as error:
        return _controlled_exception_payload(error)
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def health_check() -> str:
    """Comprueba el estado del backend a través de la herramienta interna."""
    return _run_local_tool("health_check")


@mcp.tool(annotations=MUTATION_TOOL)
def upload_document(file_path: str) -> str:
    """Sube un documento DOCX local y crea una corrida de procesamiento."""
    if not _mutations_enabled():
        return _mutation_disabled_payload("upload_document")
    try:
        args = UploadDocumentInput(file_path=file_path)
        payload = upload_document_from_path(args.file_path)
        return _as_json(_success_envelope(payload))
    except (PydanticValidationError, ValueError) as error:
        return _controlled_exception_payload(error)
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool(annotations=MUTATION_TOOL)
def process_job(job_id: int) -> str:
    """Ejecuta OCR/LLM sobre una corrida existente.

    Requiere `MCP_ENABLE_MUTATIONS=1` para evitar mutaciones accidentales desde
    asistentes en ambientes de solo consulta.
    """
    if not _mutations_enabled():
        return _mutation_disabled_payload("process_job")
    try:
        args = JobIdInput(job_id=job_id)
        return _run_local_tool(
            "process_job", {"job_id": args.job_id}, job_id=args.job_id
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=MUTATION_TOOL)
def reprocess_failed_sources(job_id: int) -> str:
    """Reprocesa solo las fuentes que quedaron fallidas."""
    if not _mutations_enabled():
        return _mutation_disabled_payload("reprocess_failed_sources")
    try:
        args = JobIdInput(job_id=job_id)
        return _run_local_tool(
            "reprocess_failed_sources",
            {"job_id": args.job_id},
            job_id=args.job_id,
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=MUTATION_TOOL)
def reprocess_source_image(
    job_id: int,
    source_image_id: int | None = None,
    deposit_id: int | None = None,
) -> str:
    """Reprocesa una fuente concreta o la fuente asociada a un depósito."""
    if not _mutations_enabled():
        return _mutation_disabled_payload("reprocess_source_image")
    try:
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
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_job_status(job_id: int) -> str:
    """Obtiene el estado detallado de una corrida con relaciones anidadas."""
    try:
        args = JobIdInput(job_id=job_id)
        return _run_local_tool(
            "get_job_status", {"job_id": args.job_id}, job_id=args.job_id
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def list_jobs() -> str:
    """Lista las corridas de procesamiento ordenadas por recencia."""
    return _run_local_tool("list_jobs")


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_job_logs(job_id: int) -> str:
    """Lista los logs de extracción de una corrida."""
    try:
        args = JobIdInput(job_id=job_id)
        return _run_local_tool(
            "get_job_logs", {"job_id": args.job_id}, job_id=args.job_id
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def list_job_logs(job_id: int) -> str:
    """Alias legado de `get_job_logs` conservado por compatibilidad."""
    return get_job_logs(job_id)


@mcp.tool(annotations=MUTATION_TOOL)
def export_job_excel(job_id: int) -> str:
    """Genera la exportación Excel de una corrida finalizada."""
    if not _mutations_enabled():
        return _mutation_disabled_payload("export_job_excel")
    try:
        args = JobIdInput(job_id=job_id)
        return _run_local_tool(
            "export_job_excel", {"job_id": args.job_id}, job_id=args.job_id
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=DESTRUCTIVE_MUTATION_TOOL)
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
        return _mutation_disabled_payload("update_deposit_correction")
    try:
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
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_processing_settings() -> str:
    """Obtiene la configuración de procesamiento activa."""
    return _run_local_tool("get_processing_settings")


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_processing_settings_options() -> str:
    """Obtiene las opciones disponibles para la configuración."""
    return _run_local_tool("get_processing_settings_options")


@mcp.tool(annotations=READ_ONLY_TOOL)
def assistant_chat(
    messages: list[dict[str, str]],
    job_id: int | None = None,
    errors: int = 0,
    query_context: dict[str, Any] | None = None,
) -> str:
    """Ejecuta el flujo de chat del asistente con el mismo contrato que la API."""
    try:
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
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=DESTRUCTIVE_MUTATION_TOOL)
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
        return _mutation_disabled_payload("update_processing_settings")
    try:
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
    except (PydanticValidationError, DrfValidationError) as error:
        return _controlled_exception_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def describe_database_schema() -> str:
    """Describe las fuentes y capacidades de consulta permitidas."""
    return _run_local_tool("describe_database_schema")


@mcp.tool(annotations=READ_ONLY_TOOL)
def query_database(query: dict[str, Any]) -> str:
    """Ejecuta una consulta estructurada segura sobre fuentes permitidas."""
    return _run_local_tool("query_database", {"query": query})


@mcp.tool(annotations=RESTRICTED_READ_TOOL)
def query_database_sql(sql: str, limit: int = 100) -> str:
    """Ejecuta una consulta SQL de solo lectura cuando está permitida."""
    if not sql.strip().lower().startswith(("select", "with")):
        return _as_json(
            _error_envelope(
                400,
                "query_database_sql is read-only",
                code="read_only_sql",
            )
        )
    return _run_local_tool("query_database_sql", {"sql": sql, "limit": limit})


@mcp.tool(annotations=DESTRUCTIVE_MUTATION_TOOL)
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
        return _mutation_disabled_payload("crud_database")
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


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_last_record_value(job_id: int | None = None) -> str:
    """Obtiene el último valor extraído de un job o del último completado."""
    try:
        arguments: dict[str, Any] = {}
        resolved_job_id: int | None = None
        if job_id is not None:
            args = JobIdInput(job_id=job_id)
            arguments["job_id"] = args.job_id
            resolved_job_id = args.job_id
        return _run_local_tool(
            "get_last_record_value", arguments, job_id=resolved_job_id
        )
    except PydanticValidationError as error:
        return _validation_error_payload(error)


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_completed_records_summary() -> str:
    """Obtiene un resumen agregado de registros completados."""
    return _run_local_tool("get_completed_records_summary")


@mcp.resource(
    "diplo://health",
    name="health",
    title="Estado del backend",
    description="Estado liviano del backend Django usado por el servidor MCP.",
    mime_type="application/json",
)
def health_resource() -> str:
    """Expone health_check como recurso de solo lectura."""
    return health_check()


@mcp.resource(
    "diplo://capabilities",
    name="capabilities",
    title="Capacidades MCP",
    description="Herramientas y capacidades disponibles con su nivel de riesgo.",
    mime_type="application/json",
)
def capabilities_resource() -> str:
    """Describe capacidades sin ejecutar mutaciones."""
    return _run_local_tool("explain_capabilities")


@mcp.resource(
    "diplo://jobs",
    name="jobs",
    title="Jobs recientes",
    description="Lista resumida de corridas recientes.",
    mime_type="application/json",
)
def jobs_resource() -> str:
    """Lista jobs recientes como recurso MCP."""
    return list_jobs()


@mcp.resource(
    "diplo://jobs/{job_id}",
    name="job_detail",
    title="Detalle de job",
    description="Detalle normalizado de una corrida por identificador.",
    mime_type="application/json",
)
def job_detail_resource(job_id: str) -> str:
    """Obtiene detalle de job desde un URI MCP."""
    try:
        return get_job_status(int(job_id))
    except ValueError as error:
        return _controlled_exception_payload(error)


@mcp.resource(
    "diplo://jobs/{job_id}/logs",
    name="job_logs",
    title="Logs de job",
    description="Logs de extracción asociados a una corrida.",
    mime_type="application/json",
)
def job_logs_resource(job_id: str) -> str:
    """Obtiene logs de job desde un URI MCP."""
    try:
        return get_job_logs(int(job_id))
    except ValueError as error:
        return _controlled_exception_payload(error)


@mcp.resource(
    "diplo://processing/settings",
    name="processing_settings",
    title="Configuración de procesamiento",
    description="Configuración activa sin claves secretas.",
    mime_type="application/json",
)
def processing_settings_resource() -> str:
    """Expone configuración saneada como recurso de solo lectura."""
    return get_processing_settings()


@mcp.prompt(
    name="diagnose_job",
    title="Diagnosticar job",
    description="Guía para investigar estado, logs y hallazgos de una corrida.",
)
def diagnose_job_prompt(job_id: int) -> str:
    """Plantilla reutilizable para diagnóstico de corridas."""
    return (
        f"Diagnostica el job #{job_id}. Primero consulta get_job_status, luego "
        "get_job_logs si hay errores o estado processing. Resume estado, etapa "
        "probable, hallazgos y siguiente accion segura. No ejecutes mutaciones "
        "sin confirmacion explicita del usuario."
    )


@mcp.prompt(
    name="explain_results",
    title="Explicar resultados",
    description="Guía para explicar depósitos extraídos y errores al usuario.",
)
def explain_results_prompt(job_id: int) -> str:
    """Plantilla para explicar resultados de una corrida."""
    return (
        f"Explica los resultados del job #{job_id} en lenguaje claro. Usa "
        "get_job_status para identificar registros, imagenes y observaciones. "
        "Distingue datos confiables de posibles errores y propone correcciones "
        "manuales cuando aplique."
    )


@mcp.prompt(
    name="prepare_reprocessing",
    title="Preparar reprocesamiento",
    description="Guía para decidir entre reproceso total o reproceso de fallidos.",
)
def prepare_reprocessing_prompt(job_id: int) -> str:
    """Plantilla para preparar reprocesos con confirmación."""
    return (
        f"Prepara un reprocesamiento para el job #{job_id}. Revisa el estado "
        "actual con get_job_status. Si el estado es completed_with_errors, "
        "prefiere reprocess_failed_sources. Si el usuario pide reproceso total, "
        "explica que process_job reejecuta la corrida. Solicita confirmacion "
        "antes de cualquier mutacion."
    )


def main() -> None:
    """Arranca el servidor MCP sobre stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
