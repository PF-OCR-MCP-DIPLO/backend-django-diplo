from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Avg, Count, Max, Min, Sum
from django.utils import timezone
from django.utils.timezone import is_aware

from apps.api.services.shared_tools import upload_document_from_path
from apps.api.services.assistant_tasks import (
    AssistantTask,
    build_assistant_task_context,
    resolve_assistant_task,
)
from apps.api.services.pending_actions import (
    build_pending_action,
    clear_pending_action,
    confirmation_message,
    normalize_pending_action,
    validate_pending_action,
)
from apps.api.services.deposit_correction_tools import (
    deposit_correction_confirmation_message,
    deposit_correction_has_updates,
    deposit_correction_failure_description,
    deposit_correction_needs_clarification,
    deposit_correction_payload_for_correction,
    deposit_correction_success_description,
    deposit_correction_summary,
    deposit_correction_values_from_arguments,
    execute_deposit_correction,
    extract_deposit_correction_deposit_id,
    normalize_deposit_correction_arguments,
)
from apps.api.serializers import (
    ExtractionLogSerializer,
    ProcessingSettingsSerializer,
    ProcessRunDetailSerializer,
    ProcessRunListSerializer,
)
from apps.api.services.assistant_llm import (
    AssistantProviderError,
    AssistantTextClient,
    TextGenerationConfig,
)
from apps.api.services.tool_risk import get_tool_risk_level, tool_requires_confirmation
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    SourceImage,
)
from apps.processing.services.excel_exporter import export_job_to_excel
from apps.processing.services.orchestrator import process_job
from apps.processing.services.settings_service import (
    available_options,
    get_or_create_processing_settings,
    get_runtime_config,
)

_ALLOWED_TOOLS = {
    "none",
    "health_check",
    "describe_database_schema",
    "query_database_sql",
    "list_jobs",
    "get_job_status",
    "get_job_logs",
    "get_last_record_value",
    "get_completed_records_summary",
    "query_database",
    "crud_database",
    "update_deposit_correction",
    "get_processing_settings",
    "get_processing_settings_options",
    "update_processing_settings",
    "process_job",
    "export_job_excel",
    "upload_document",
    "list_available_tools",
    "explain_capabilities",
    "help",
}

_CAPABILITIES = [
    "Consultar jobs, estados, logs y errores de procesamiento.",
    "Buscar datos de consignaciones con lenguaje natural.",
    "Corregir registros por id o filtros.",
    "Actualizar configuración de OCR, LLM y chatbot.",
    "Procesar jobs y exportar Excel.",
]

_CONFIRMATION_WORDS = {
    "confirmo",
    "confirmar",
    "confirma",
    "si",
    "sí",
    "ok",
    "dale",
    "ejecuta",
    "ejecutar",
    "adelante",
}

_CANCEL_WORDS = {"cancelar", "cancela", "no", "anular", "detener"}

logger = logging.getLogger(__name__)


def _assistant_memory_recommendation() -> str:
    return (
        "El modelo local configurado no cabe en la memoria disponible. "
        "Para equipos con poca RAM usa qwen3:1.7b. "
        "Si tienes más memoria disponible, llama3.2:3b puede ser una alternativa."
    )


def _normalize_query_context(raw_query_context: Any) -> dict[str, Any]:
    if not isinstance(raw_query_context, dict):
        return {}
    return dict(raw_query_context)


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


_RE_WORD_LIMIT = re.compile(r"\b(\d{1,3})\b")
_RE_ID_FILTER = re.compile(r"(?:id\s*#?|id:)\s*(\d+)")
_RE_AMOUNT_AFTER_PREFIX = re.compile(r"(?:a|por)\s*\$\s*([\d\.,]+)")
_RE_REFERENCE_FILTER = re.compile(r"referencia\s*[:#]?\s*([a-z0-9\-]{4,})")
_RE_YEAR = re.compile(r"\b(20\d{2})\b")
_RE_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _allow_unsafe_sql_enabled() -> bool:
    return False


def _mutation_tools_enabled() -> bool:
    return bool(getattr(settings, "MCP_ENABLE_MUTATIONS", False))


def _confirmation_payload(
    tool: str, detail: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "detail": detail,
        "tool": tool,
        "requires_confirmation": True,
        "risk_level": get_tool_risk_level(tool),
        "arguments": arguments or {},
    }


@dataclass(frozen=True)
class AssistantIntent:
    name: str
    confidence: float
    tool_hint: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class AssistantPlan:
    tool: str
    arguments: dict[str, Any]
    intent_name: str
    intent_summary: str


class IntentAgent:
    _MONTHS = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    def __init__(
        self,
        model: str,
        timeout: int,
        provider: str,
        api_key: str = "",
        text_client: AssistantTextClient | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.provider = provider
        self.api_key = api_key
        self.text_client = text_client or AssistantTextClient()

    def infer(
        self,
        messages: list[dict[str, str]],
        job_id: int | None,
        errors: int,
    ) -> AssistantIntent:
        last_user_message = self._last_user_message(messages)
        if not last_user_message:
            return AssistantIntent(
                name="unknown", confidence=0.0, summary="Sin mensaje del usuario"
            )

        if self._looks_like_greeting(last_user_message):
            return AssistantIntent(
                name="generic_chat",
                confidence=0.99,
                tool_hint="none",
                summary="Saludo o charla general",
            )

        direct_intent = self._infer_direct_intent(
            last_user_message,
            job_id,
        )
        if direct_intent is not None:
            return direct_intent
        if self._matches_capabilities_request(last_user_message):
            return AssistantIntent(
                name="capabilities",
                confidence=0.99,
                tool_hint="explain_capabilities",
                summary="Pregunta de capacidades o ayuda",
            )

        return self._infer_with_llm(messages, job_id=job_id, errors=errors)

    def _last_user_message(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return _normalize_text(message.get("content") or "")
        return ""

    def _infer_direct_intent(
        self,
        text: str,
        job_id: int | None,
    ) -> AssistantIntent | None:
        crud_intent = self._infer_crud_intent(text)
        if crud_intent is not None:
            return crud_intent

        transactions_intent = self._infer_transactions_query_intent(text)
        if transactions_intent is not None:
            return transactions_intent

        if self._matches_completed_records_total(text):
            return AssistantIntent(
                name="completed_records_total",
                confidence=0.99,
                tool_hint="get_completed_records_summary",
                arguments={"job_id": job_id} if job_id is not None else {},
                summary="Pregunta por el total acumulado de los registros completados",
            )

        if self._matches_count_records(text):
            return AssistantIntent(
                name="count_records",
                confidence=0.95,
                tool_hint="query_database",
                arguments={
                    "query": {
                        "source": "deposits",
                        "aggregations": [
                            {"type": "count", "field": "id", "as": "total_records"}
                        ],
                    }
                },
                summary="Pregunta por la cantidad total de registros",
            )

        if self._matches_latest_records(text):
            return AssistantIntent(
                name="db_query",
                confidence=0.96,
                tool_hint="query_database",
                arguments={
                    "query": {
                        "source": "deposits",
                        "select": [
                            "id",
                            "process_run_id",
                            "referencia",
                            "valor",
                            "fecha_consignacion",
                            "hora_consignacion",
                            "created_at",
                        ],
                        "order_by": [{"field": "created_at", "direction": "desc"}],
                        "limit": self._extract_limit(text),
                    }
                },
                summary="Pregunta por los ultimos registros extraidos",
            )

        if self._matches_last_record_value(text):
            return AssistantIntent(
                name="last_record_value",
                confidence=0.98,
                tool_hint="get_last_record_value",
                arguments={"job_id": job_id} if job_id is not None else {},
                summary="Pregunta por el valor del ultimo registro",
            )

        if self._matches_recent_jobs(text):
            return AssistantIntent(
                name="recent_jobs",
                confidence=0.92,
                tool_hint="list_jobs",
                summary="Pregunta por jobs recientes",
            )

        if self._matches_job_status(text):
            return AssistantIntent(
                name="job_status",
                confidence=0.84,
                tool_hint="get_job_status",
                arguments={"job_id": job_id} if job_id is not None else {},
                summary="Pregunta por el estado de un job",
            )

        if self._matches_job_logs(text):
            return AssistantIntent(
                name="job_logs",
                confidence=0.84,
                tool_hint="get_job_logs",
                arguments={"job_id": job_id} if job_id is not None else {},
                summary="Pregunta por logs de un job",
            )

        if self._matches_settings(text):
            return AssistantIntent(
                name="settings",
                confidence=0.86,
                tool_hint="get_processing_settings",
                summary="Pregunta por la configuracion del procesamiento",
            )

        if self._matches_database_schema(text):
            return AssistantIntent(
                name="db_schema",
                confidence=0.92,
                tool_hint="describe_database_schema",
                summary="Pregunta por tablas/campos disponibles para consultas",
            )

        if self._matches_sql_query(text):
            return AssistantIntent(
                name="sql_query",
                confidence=0.93,
                tool_hint="query_database_sql",
                arguments={"sql": "", "limit": 100},
                summary="Consulta SQL solicitada por el usuario",
            )

        if self._matches_followup_query(text):
            return AssistantIntent(
                name="unknown",
                confidence=0.75,
                tool_hint="none",
                summary="Solicitud de seguimiento ambigua sin consulta completa",
            )

        return None

    def _matches_last_record_value(self, text: str) -> bool:
        value_terms = ("valor", "monto", "importe")
        record_terms = (
            "ultimo registro",
            "último registro",
            "ultima consignacion",
            "última consignación",
            "ultimo deposito",
            "último depósito",
            "ultimo valor",
            "último valor",
        )
        return _contains_any(text, value_terms) and _contains_any(text, record_terms)

    def _matches_latest_records(self, text: str) -> bool:
        return (
            "registro" in text
            and _contains_any(text, ("ultimos", "últimos", "recientes", "latest"))
            and not _contains_any(text, ("valor", "monto", "importe"))
        )

    def _extract_limit(self, text: str) -> int:
        match = _RE_WORD_LIMIT.search(text)
        if match:
            try:
                return max(1, min(int(match.group(1)), 50))
            except ValueError:
                pass

        words_to_numbers = {
            "uno": 1,
            "una": 1,
            "dos": 2,
            "tres": 3,
            "cuatro": 4,
            "cinco": 5,
            "seis": 6,
            "siete": 7,
            "ocho": 8,
            "nueve": 9,
            "diez": 10,
        }
        for word, number in words_to_numbers.items():
            if re.search(rf"\b{word}\b", text):
                return number
        return 5

    def _infer_crud_intent(self, text: str) -> AssistantIntent | None:
        if not _contains_any(
            text,
            (
                "transaccion",
                "transacción",
                "registro",
                "deposito",
                "depósito",
                "bd",
                "base de datos",
            ),
        ):
            return None

        if _contains_any(text, ("crear", "crea", "inserta", "agrega", "registrar")):
            values: dict[str, Any] = {}
            reference = self._extract_reference_filter(text)
            if reference and isinstance(reference.get("value"), str):
                values["referencia"] = reference["value"]
            exact_amount = self._extract_transaction_amount_filters(text)
            for item in exact_amount:
                if item.get("op") == "eq":
                    values["valor"] = item.get("value")

            process_run_match = re.search(
                r"(?:job|process_run(?:_id)?|proceso)\s*#?\s*(\d+)", text
            )
            if process_run_match:
                values["process_run_id"] = int(process_run_match.group(1))

            source_image_match = re.search(
                r"(?:imagen|image|source_image(?:_id)?)\s*#?\s*(\d+)", text
            )
            if source_image_match:
                values["source_image_id"] = int(source_image_match.group(1))

            sequence_match = re.search(
                r"(?:secuencia|sequence|indice|índice)\s*#?\s*(\d+)", text
            )
            if sequence_match:
                values["sequence_index"] = int(sequence_match.group(1))

            return AssistantIntent(
                name="crud_create",
                confidence=0.9,
                tool_hint="crud_database",
                arguments={
                    "operation": "create",
                    "source": "deposits",
                    "values": values,
                },
                summary="Solicitud de creacion de registro",
            )

        if _contains_any(
            text,
            ("actualiza", "actualizar", "editar", "modificar", "cambiar"),
        ):
            filters: list[dict[str, Any]] = []
            values: dict[str, Any] = {}

            id_match = _RE_ID_FILTER.search(text)
            if id_match:
                filters.append(
                    {"field": "id", "op": "eq", "value": int(id_match.group(1))}
                )

            ref_filter = self._extract_reference_filter(text)
            if ref_filter is not None:
                filters.append(ref_filter)

            amount_match = _RE_AMOUNT_AFTER_PREFIX.search(text)
            if amount_match:
                parsed_amount = self._to_numeric_amount(amount_match.group(1))
                if parsed_amount is not None:
                    values["valor"] = parsed_amount

            return AssistantIntent(
                name="crud_update",
                confidence=0.9,
                tool_hint="crud_database",
                arguments={
                    "operation": "update",
                    "source": "deposits",
                    "filters": filters,
                    "values": values,
                },
                summary="Solicitud de actualizacion de registro",
            )

        if _contains_any(text, ("corrige", "corregir", "corrección", "correccion")):
            deposit_id = extract_deposit_correction_deposit_id(text)
            if deposit_id is not None:
                return AssistantIntent(
                    name="deposit_correction",
                    confidence=0.92,
                    tool_hint="update_deposit_correction",
                    arguments={"deposit_id": deposit_id},
                    summary=deposit_correction_summary({"deposit_id": deposit_id}),
                )

        if _contains_any(text, ("elimina", "eliminar", "borra", "borrar")):
            filters: list[dict[str, Any]] = []
            id_match = _RE_ID_FILTER.search(text)
            if id_match:
                filters.append(
                    {"field": "id", "op": "eq", "value": int(id_match.group(1))}
                )

            ref_filter = self._extract_reference_filter(text)
            if ref_filter is not None:
                filters.append(ref_filter)

            return AssistantIntent(
                name="crud_delete",
                confidence=0.9,
                tool_hint="crud_database",
                arguments={
                    "operation": "delete",
                    "source": "deposits",
                    "filters": filters,
                },
                summary="Solicitud de eliminacion de registro",
            )

        return None

    def _infer_transactions_query_intent(self, text: str) -> AssistantIntent | None:
        if not self._looks_like_transaction_query(text):
            return None

        query: dict[str, Any] = {
            "source": "deposits",
            "select": [
                "id",
                "process_run_id",
                "referencia",
                "valor",
                "fecha_consignacion",
                "hora_consignacion",
                "created_at",
            ],
            "filters": [],
            "order_by": [{"field": "created_at", "direction": "desc"}],
            "limit": 30,
        }

        date_filters = self._extract_transaction_date_filters(text)
        if date_filters:
            query["filters"].extend(date_filters)

        amount_filters = self._extract_transaction_amount_filters(text)
        if amount_filters:
            query["filters"].extend(amount_filters)

        reference_filter = self._extract_reference_filter(text)
        if reference_filter is not None:
            query["filters"].append(reference_filter)

        if self._is_group_by_day_request(text):
            query["group_by"] = ["fecha_consignacion"]
            query["aggregations"] = [
                {"type": "count", "field": "id", "as": "total_transacciones"},
                {"type": "sum", "field": "valor", "as": "total_valor"},
            ]
            query["order_by"] = [{"field": "fecha_consignacion", "direction": "desc"}]
            query["limit"] = 60

        if self._is_total_sum_request(text):
            query["select"] = []
            query["aggregations"] = [
                {"type": "sum", "field": "valor", "as": "total_valor"}
            ]
            query.pop("order_by", None)
            query["limit"] = 1

        if self._is_average_request(text):
            query["select"] = []
            query["aggregations"] = [
                {"type": "avg", "field": "valor", "as": "promedio_valor"}
            ]
            query.pop("order_by", None)
            query["limit"] = 1

        if self._is_count_request(text):
            query["select"] = []
            query["aggregations"] = [
                {"type": "count", "field": "id", "as": "total_transacciones"}
            ]
            query.pop("order_by", None)
            query["limit"] = 1

        if self._is_references_only_request(text):
            query["select"] = [
                "referencia",
                "valor",
                "fecha_consignacion",
                "created_at",
            ]

        if self._is_sort_by_amount_desc_request(text):
            query["order_by"] = [{"field": "valor", "direction": "desc"}]
        elif self._is_sort_by_amount_asc_request(text):
            query["order_by"] = [{"field": "valor", "direction": "asc"}]
        elif self._is_sort_by_date_desc_request(text):
            query["order_by"] = [{"field": "created_at", "direction": "desc"}]

        if "ultima" in text or "última" in text or "ultimo" in text or "último" in text:
            query["order_by"] = [{"field": "created_at", "direction": "desc"}]

        if self._is_all_transactions_request(text):
            query["limit"] = 200

        if self._is_top_transactions_request(text):
            query["order_by"] = [{"field": "valor", "direction": "desc"}]
            query["limit"] = self._extract_limit(text)
        elif self._has_explicit_limit_request(text):
            query["limit"] = self._extract_limit(text)

        return AssistantIntent(
            name="db_query",
            confidence=0.95,
            tool_hint="query_database",
            arguments={"query": query},
            summary="Consulta transaccional interpretada en lenguaje natural",
        )

    def _looks_like_transaction_query(self, text: str) -> bool:
        transaction_terms = (
            "transaccion",
            "transacciones",
            "transferencia",
            "transferencias",
            "movimiento",
            "movimientos",
            "referencia",
            "referencias",
            "cuanto movi",
            "cuánto moví",
            "lo ultimo que hice",
            "lo último que hice",
        )
        action_terms = (
            "dame",
            "muestr",
            "lista",
            "busca",
            "encuentra",
            "cuanto",
            "cuánto",
            "promedio",
            "suma",
            "cantidad",
            "ordena",
            "agrupa",
            "ultim",
            "entre",
            "mayor",
            "menor",
            "esta semana",
            "este mes",
            "ultimo mes",
            "último mes",
            "este año",
        )
        return _contains_any(text, transaction_terms) or (
            _contains_any(text, action_terms)
            and _contains_any(
                text, ("$", "mes", "semana", "fecha", "abril", "enero", "marzo")
            )
        )

    def _has_explicit_limit_request(self, text: str) -> bool:
        return _contains_any(
            text,
            ("ultimas", "últimas", "ultimos", "últimos", "top", "primeras", "primeros"),
        ) and bool(_RE_WORD_LIMIT.search(text))

    def _is_all_transactions_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "todas las transacciones",
                "todos los movimientos",
                "todas las transferencias",
            ),
        )

    def _is_top_transactions_request(self, text: str) -> bool:
        return _contains_any(
            text,
            ("mas altas", "más altas", "mas grandes", "más grandes", "top"),
        )

    def _is_references_only_request(self, text: str) -> bool:
        return "referencia" in text and _contains_any(
            text,
            (
                "dame las referencias",
                "muestrame las referencias",
                "muéstrame las referencias",
                "referencias entre",
            ),
        )

    def _is_total_sum_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "cuanto es la cuenta en total",
                "cuánto es la cuenta en total",
                "suma de transacciones",
                "suma total",
                "cuanto movi",
                "cuánto moví",
                "cuanto movi en estos dias",
                "cuánto moví en estos días",
            ),
        )

    def _is_average_request(self, text: str) -> bool:
        return "promedio" in text

    def _is_count_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "cantidad de transacciones",
                "cuantas transacciones",
                "cuántas transacciones",
                "numero de transacciones",
                "número de transacciones",
            ),
        )

    def _is_group_by_day_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "agrupalas por dia",
                "agrúpalas por día",
                "agrupar por dia",
                "agrupar por día",
            ),
        )

    def _is_sort_by_amount_desc_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "de mayor a menor valor",
                "mayor a menor valor",
                "ordenalas de mayor a menor",
                "ordénalas de mayor a menor",
            ),
        )

    def _is_sort_by_amount_asc_request(self, text: str) -> bool:
        return _contains_any(text, ("de menor a mayor valor", "menor a mayor valor"))

    def _is_sort_by_date_desc_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "fecha descendente",
                "por fecha descendente",
                "mas recientes",
                "más recientes",
                "lo ultimo que hice",
                "lo último que hice",
            ),
        )

    def _extract_reference_filter(self, text: str) -> dict[str, Any] | None:
        pattern = _RE_REFERENCE_FILTER.search(text)
        if not pattern:
            return None
        reference = pattern.group(1).strip()
        return {"field": "referencia", "op": "icontains", "value": reference}

    def _extract_transaction_amount_filters(self, text: str) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []

        for keyword in ("mayores a", "mayor a", "mas de", "más de", "superiores a"):
            amount = self._extract_amount_after_keyword(text, keyword)
            if amount is not None:
                filters.append({"field": "valor", "op": "gt", "value": amount})
                break

        for keyword in ("menores a", "menor a", "menos de", "inferiores a"):
            amount = self._extract_amount_after_keyword(text, keyword)
            if amount is not None:
                filters.append({"field": "valor", "op": "lt", "value": amount})
                break

        near_match = re.search(
            r"(?:cercan[ao]s?\s+a|cerca\s+de)\s*\$?\s*([\d\.,]+)", text
        )
        if near_match:
            amount = self._to_numeric_amount(near_match.group(1))
            if amount is not None:
                delta = max(1, int(amount * 0.1))
                filters.append(
                    {
                        "field": "valor",
                        "op": "between",
                        "value": [max(amount - delta, 0), amount + delta],
                    }
                )

        exact_match = re.search(r"por\s*\$\s*([\d\.,]+)", text)
        if exact_match:
            amount = self._to_numeric_amount(exact_match.group(1))
            if amount is not None:
                filters.append({"field": "valor", "op": "eq", "value": amount})

        return filters

    def _extract_amount_after_keyword(self, text: str, keyword: str) -> int | None:
        pattern = re.search(rf"{re.escape(keyword)}\s*\$?\s*([\d\.,]+)", text)
        if not pattern:
            return None
        return self._to_numeric_amount(pattern.group(1))

    def _to_numeric_amount(self, raw_value: str) -> int | None:
        digits = re.sub(r"[^\d]", "", raw_value or "")
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _extract_transaction_date_filters(self, text: str) -> list[dict[str, Any]]:
        today = timezone.localdate()
        filters: list[dict[str, Any]] = []

        range_dates = self._extract_between_dates(text)
        if range_dates is not None:
            start_date, end_date = range_dates
            filters.extend(
                [
                    {
                        "field": "created_at",
                        "op": "date_gte",
                        "value": start_date.isoformat(),
                    },
                    {
                        "field": "created_at",
                        "op": "date_lte",
                        "value": end_date.isoformat(),
                    },
                ]
            )
            return filters

        exact_date = self._extract_exact_spanish_date(text)
        if exact_date is not None:
            filters.append(
                {
                    "field": "created_at",
                    "op": "date_eq",
                    "value": exact_date.isoformat(),
                }
            )
            return filters

        if "ultimo mes" in text or "último mes" in text:
            filters.append({"field": "created_at", "op": "in_last_days", "value": 30})
            return filters

        if "esta semana" in text or "esta semana" in text:
            filters.append({"field": "created_at", "op": "in_last_days", "value": 7})
            return filters

        if "estos dias" in text or "estos días" in text:
            filters.append({"field": "created_at", "op": "in_last_days", "value": 7})
            return filters

        if "este mes" in text:
            start = today.replace(day=1)
            filters.extend(
                [
                    {
                        "field": "created_at",
                        "op": "date_gte",
                        "value": start.isoformat(),
                    },
                    {
                        "field": "created_at",
                        "op": "date_lte",
                        "value": today.isoformat(),
                    },
                ]
            )
            return filters

        if "este año" in text or "este ano" in text:
            start = today.replace(month=1, day=1)
            filters.extend(
                [
                    {
                        "field": "created_at",
                        "op": "date_gte",
                        "value": start.isoformat(),
                    },
                    {
                        "field": "created_at",
                        "op": "date_lte",
                        "value": today.isoformat(),
                    },
                ]
            )
            return filters

        month_name = self._extract_month_name(text)
        if month_name is not None:
            year = self._extract_year(text) or today.year
            month = self._MONTHS[month_name]
            start = date(year, month, 1)
            if month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month + 1, 1) - timedelta(days=1)
            filters.extend(
                [
                    {
                        "field": "created_at",
                        "op": "date_gte",
                        "value": start.isoformat(),
                    },
                    {"field": "created_at", "op": "date_lte", "value": end.isoformat()},
                ]
            )
        return filters

    def _extract_exact_spanish_date(self, text: str) -> date | None:
        match = re.search(
            r"\b(?:del|de)?\s*(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?\b",
            text,
        )
        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3)) if match.group(3) else timezone.localdate().year
        month = self._MONTHS.get(month_name)
        if month is None:
            return None
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _extract_between_dates(self, text: str) -> tuple[date, date] | None:
        explicit_days = re.search(
            r"entre\s+(?:el\s+)?(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?\s+y\s+(?:el\s+)?(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?",
            text,
        )
        if explicit_days:
            start_year = (
                int(explicit_days.group(3))
                if explicit_days.group(3)
                else timezone.localdate().year
            )
            end_year = (
                int(explicit_days.group(6)) if explicit_days.group(6) else start_year
            )
            start_month = self._MONTHS[explicit_days.group(2)]
            end_month = self._MONTHS[explicit_days.group(5)]
            try:
                start = date(start_year, start_month, int(explicit_days.group(1)))
                end = date(end_year, end_month, int(explicit_days.group(4)))
                return (start, end) if start <= end else (end, start)
            except ValueError:
                return None

        months_range = re.search(
            r"entre\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
            r"\s+y\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?",
            text,
        )
        if months_range:
            year = (
                int(months_range.group(3))
                if months_range.group(3)
                else timezone.localdate().year
            )
            start_month = self._MONTHS[months_range.group(1)]
            end_month = self._MONTHS[months_range.group(2)]
            start = date(year, min(start_month, end_month), 1)
            last_month = max(start_month, end_month)
            if last_month == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, last_month + 1, 1) - timedelta(days=1)
            return start, end

        return None

    def _extract_month_name(self, text: str) -> str | None:
        for month_name in self._MONTHS:
            if re.search(rf"\b{month_name}\b", text):
                return month_name
        return None

    def _extract_year(self, text: str) -> int | None:
        match = _RE_YEAR.search(text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _matches_completed_records_total(self, text: str) -> bool:
        total_terms = (
            "total de todos los registros completados",
            "total de registros completados",
            "suma de registros completados",
            "suma de los registros completados",
            "monto total de los registros completados",
            "valor total de los registros completados",
            "total acumulado",
            "cuanto suman",
            "cuánto suman",
            "todos los registros completados",
        )
        return _contains_any(text, total_terms)

    def _matches_count_records(self, text: str) -> bool:
        count_terms = (
            "cuántos registros",
            "cuantos registros",
            "número de registros",
            "numero de registros",
            "cantidad de registros",
            "total de registros",
            "cuántas transacciones",
            "cuantas transacciones",
            "cuántos depositos",
            "cuantos depositos",
            "cuántas consignaciones",
            "cuantas consignaciones",
        )
        return _contains_any(text, count_terms)

    def _matches_recent_jobs(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "jobs recientes",
                "ultimos jobs",
                "últimos jobs",
                "listar jobs",
                "lista de jobs",
                "ver jobs",
            ),
        )

    def _matches_job_status(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "estado del job",
                "estado del ultimo job",
                "status del job",
                "resultado del job",
            ),
        )

    def _matches_job_logs(self, text: str) -> bool:
        return _contains_any(
            text, ("logs", "bitacora", "historial de logs", "ver logs")
        )

    def _matches_settings(self, text: str) -> bool:
        return _contains_any(
            text, ("configuracion", "configuración", "settings", "ajustes")
        )

    def _matches_capabilities_request(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "que puedes hacer",
                "qué puedes hacer",
                "que herramientas",
                "qué herramientas",
                "herramientas tienes",
                "comandos",
                "mcp",
            ),
        )

    def _looks_like_greeting(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "hola",
                "buenas",
                "buenos dias",
                "buenos días",
                "hey",
                "saludos",
            ),
        )

    def _matches_database_schema(self, text: str) -> bool:
        return _contains_any(
            text,
            (
                "que se puede consultar",
                "qué se puede consultar",
                "que tablas",
                "qué tablas",
                "que campos",
                "qué campos",
                "estructura de la base de datos",
                "schema",
                "esquema",
            ),
        )

    def _matches_sql_query(self, text: str) -> bool:
        return _contains_any(
            text,
            ("sql", "sentencia sql", "consulta sql", "query sql", "haz un select"),
        )

    def _matches_followup_query(self, text: str) -> bool:
        followup_terms = (
            "solo",
            "ahora",
            "filtra",
            "del ultimo",
            "del último",
            "de este",
            "de esos",
            "solo los",
            "solo las",
            "y ahora",
        )
        return _contains_any(text, followup_terms)

    def _infer_with_llm(
        self, messages: list[dict[str, str]], job_id: int | None, errors: int
    ) -> AssistantIntent:
        prompt = f"""
Eres un agente de intencion para un dashboard de procesamiento.

Contexto:
- job_id_actual: {job_id if job_id is not None else 'null'}
- errores_detectados: {errors}

Clasifica el ultimo mensaje del usuario en uno de estos intentos:
- last_record_value
- completed_records_total
- count_records
- recent_jobs
- job_status
- job_logs
- settings
- process_job
- export_job
- db_schema
- sql_query
- db_query
- crud_create
- crud_update
- crud_delete
- generic_chat

Responde SOLO con JSON valido y nada mas usando este esquema:
{{
    "intent": "...",
    "tool_hint": "...|null",
  "confidence": 0.0,
  "summary": "...",
  "arguments": {{ ... }}
}}

Ultimo mensaje del usuario: {self._last_user_message(messages)}
""".strip()

        raw_response = self._generate_text(prompt)
        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            return AssistantIntent(
                name="unknown", confidence=0.0, summary="Clasificacion no disponible"
            )

        intent = str(payload.get("intent") or "unknown").strip()
        tool_hint = payload.get("tool_hint")
        if tool_hint == "null":
            tool_hint = None
        if tool_hint is not None:
            tool_hint = str(tool_hint).strip()
            if tool_hint not in _ALLOWED_TOOLS:
                tool_hint = None

        arguments = payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        confidence = payload.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        summary = str(payload.get("summary") or intent)
        if tool_hint and "job_id" not in arguments and job_id is not None:
            arguments["job_id"] = job_id

        return AssistantIntent(
            name=intent or "unknown",
            confidence=confidence,
            tool_hint=tool_hint,
            arguments=arguments,
            summary=summary,
        )

    def _format_conversation(self, messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for message in messages[-8:]:
            role = message.get("role", "user")
            content = (message.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _generate_text(self, prompt: str) -> str:
        return self.text_client.generate(
            prompt,
            TextGenerationConfig(
                provider=self.provider,
                model=self.model,
                timeout=self.timeout,
                api_key=self.api_key,
                temperature=0.1,
                num_predict=256,
            ),
        )

    def _extract_json(self, text: str) -> Any:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = _RE_JSON_OBJECT.search(cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            return None


class PlanningAgent:
    def __init__(
        self,
        model: str,
        timeout: int,
        provider: str,
        api_key: str = "",
        text_client: AssistantTextClient | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.provider = provider
        self.api_key = api_key
        self.text_client = text_client or AssistantTextClient()

    def _last_user_message(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return _normalize_text(message.get("content") or "")
        return ""

    def plan(
        self,
        intent: AssistantIntent,
        messages: list[dict[str, str]],
        job_id: int | None,
        errors: int,
    ) -> AssistantPlan:
        if intent.tool_hint:
            arguments = dict(intent.arguments)
            if (
                intent.tool_hint
                in {
                    "get_job_status",
                    "get_job_logs",
                    "get_last_record_value",
                    "get_completed_records_summary",
                    "query_database",
                    "update_deposit_correction",
                    "process_job",
                    "export_job_excel",
                }
                and "job_id" not in arguments
                and job_id is not None
            ):
                arguments["job_id"] = job_id
            if intent.tool_hint == "query_database":
                arguments["query"] = arguments.get("query") or {}
            return AssistantPlan(
                tool=intent.tool_hint,
                arguments=arguments,
                intent_name=intent.name,
                intent_summary=intent.summary,
            )

        conversation = self._last_user_message(messages)
        if intent.name in {"capabilities", "help", "generic_chat"}:
            return AssistantPlan(
                tool="none",
                arguments={},
                intent_name=intent.name,
                intent_summary=intent.summary,
            )
        sql_mode_rules = (
            "- query_database_sql permite SQL libre para pruebas."
            if _allow_unsafe_sql_enabled()
            else "\n".join(
                [
                    "- query_database_sql solo permite SQL de lectura (SELECT o WITH ... SELECT).",
                    "- No uses INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, PRAGMA ni multiples sentencias.",
                ]
            )
        )
        prompt = f"""
Eres un agente planificador de herramientas para un dashboard de procesamiento.

Contexto:
- intent_detectado: {intent.name}
- resumen_intencion: {intent.summary}
- job_id_actual: {job_id if job_id is not None else 'null'}
- errores_detectados: {errors}

Herramientas disponibles:
- health_check
- describe_database_schema
- query_database_sql
- list_jobs
- get_job_status
- get_job_logs
- get_last_record_value
- get_completed_records_summary
- query_database
- crud_database
- update_deposit_correction
- get_processing_settings
- get_processing_settings_options
- update_processing_settings
- process_job
- export_job_excel

Responde SOLO con JSON valido y nada mas usando este esquema:
{{
    "tool": "none|health_check|describe_database_schema|query_database_sql|list_jobs|get_job_status|get_job_logs|get_last_record_value|get_completed_records_summary|query_database|crud_database|update_deposit_correction|get_processing_settings|get_processing_settings_options|update_processing_settings|process_job|export_job_excel",
  "arguments": {{ ... }}
}}

Reglas:
- Usa "none" si no hace falta ejecutar ninguna herramienta.
- Si la intencion es recent_jobs, usa list_jobs.
- Si la intencion es last_record_value, usa get_last_record_value.
- Si la intencion es completed_records_total, usa get_completed_records_summary.
- Si la intencion es count_records, usa query_database con una agregacion de tipo count.
- Si la intencion es db_schema, usa describe_database_schema.
- Si la intencion es sql_query, usa query_database_sql con arguments.sql.
- Si la intencion es db_query, usa query_database con un objeto `query` en arguments.
- Si la intencion es crud_create|crud_update|crud_delete, usa crud_database.
- Si la intencion es deposit_correction, usa update_deposit_correction.
- Si la intencion es job_status, usa get_job_status.
- Si la intencion es job_logs, usa get_job_logs.
- {sql_mode_rules}

Esquema de `arguments` para query_database_sql:
{{
    "sql": "SELECT ...",
    "limit": 100
}}

Esquema de `arguments.query` para query_database:
{{
    "source": "process_runs|deposits|source_images|logs",
    "select": ["field1", "field2"],
    "filters": [{{"field": "status", "op": "eq|ne|in|not_in|gt|gte|lt|lte|between|contains|icontains|startswith|istartswith|endswith|iendswith|isnull|date_eq|date_gte|date_lte|in_last_days", "value": "..."}}],
    "aggregations": [{{"type": "count|distinct_count|sum|avg|min|max", "field": "id|valor|total_records", "as": "alias"}}],
    "group_by": ["field"],
    "order_by": [{{"field": "created_at", "direction": "asc|desc"}}],
    "limit": 50
}}

Conversacion:
{conversation}
""".strip()

        raw_response = self._generate_text(prompt)
        payload = self._extract_json(raw_response)
        if not isinstance(payload, dict):
            return AssistantPlan(
                tool="none",
                arguments={},
                intent_name=intent.name,
                intent_summary=intent.summary,
            )

        tool = str(payload.get("tool") or "none").strip()
        if tool not in _ALLOWED_TOOLS:
            tool = "none"

        arguments = payload.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        if (
            tool
            in {
                "get_job_status",
                "get_job_logs",
                "get_last_record_value",
                "query_database",
                "crud_database",
                "update_deposit_correction",
                "process_job",
                "export_job_excel",
            }
            and "job_id" not in arguments
            and job_id is not None
        ):
            arguments["job_id"] = job_id

        if tool == "query_database":
            arguments["query"] = arguments.get("query") or {}

        return AssistantPlan(
            tool=tool,
            arguments=arguments,
            intent_name=intent.name,
            intent_summary=intent.summary,
        )

    def _generate_text(self, prompt: str) -> str:
        return self.text_client.generate(
            prompt,
            TextGenerationConfig(
                provider=self.provider,
                model=self.model,
                timeout=self.timeout,
                api_key=self.api_key,
                temperature=0.15,
                num_predict=256,
            ),
        )

    def _format_conversation(self, messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for message in messages[-8:]:
            role = message.get("role", "user")
            content = (message.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _extract_json(self, text: str) -> Any:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = _RE_JSON_OBJECT.search(cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            return None


_QUERY_SOURCES: dict[str, dict[str, Any]] = {
    "process_runs": {
        "model": ProcessRun,
        "fields": {
            "id",
            "original_filename",
            "status",
            "total_images",
            "total_records",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        },
    },
    "deposits": {
        "model": ExtractedDeposit,
        "fields": {
            "id",
            "process_run_id",
            "source_image_id",
            "sequence_index",
            "fecha_consignacion",
            "hora_consignacion",
            "referencia",
            "valor",
            "is_current_month",
            "created_at",
            "process_run__status",
            "process_run__original_filename",
        },
    },
    "source_images": {
        "model": SourceImage,
        "fields": {
            "id",
            "process_run_id",
            "sequence_index",
            "source_name",
            "content_hash",
            "ocr_status",
            "ocr_provider",
            "error_message",
            "created_at",
            "updated_at",
            "process_run__status",
            "process_run__original_filename",
        },
    },
    "logs": {
        "model": ExtractionLog,
        "fields": {
            "id",
            "process_run_id",
            "source_image_id",
            "sequence_index",
            "stage",
            "provider",
            "model",
            "ocr_mode",
            "notes",
            "is_error",
            "created_at",
        },
    },
}


_SUPPORTED_FILTER_OPS = [
    "eq",
    "ne",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "isnull",
    "date_eq",
    "date_gte",
    "date_lte",
    "in_last_days",
]

_SUPPORTED_AGGREGATIONS = [
    "count",
    "distinct_count",
    "sum",
    "avg",
    "min",
    "max",
]


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat() if not is_aware(value) else value.isoformat()
        except Exception:
            return str(value)
    return value


class ToolExecutionAgent:
    def execute(self, plan: AssistantPlan, job_id: int | None) -> Any:
        if plan.tool == "none":
            return {"kind": "none"}

        if plan.tool == "health_check":
            return {"status": "ok", "service": "backend-django-diplo"}

        if plan.tool == "describe_database_schema":
            return self._describe_database_schema()

        if plan.tool == "query_database_sql":
            return self._execute_query_database_sql(plan.arguments)

        if plan.tool == "query_database":
            return self._execute_query_database(plan.arguments.get("query"))

        if plan.tool == "crud_database":
            if not _mutation_tools_enabled():
                return {"detail": "crud_database is disabled by server configuration."}
            return self._execute_crud_database(plan.arguments)

        if plan.tool == "update_deposit_correction":
            if not _mutation_tools_enabled():
                return {
                    "detail": "update_deposit_correction is disabled by server configuration."
                }
            return execute_deposit_correction(plan.arguments)

        if plan.tool == "list_jobs":
            jobs = ProcessRun.objects.order_by("-created_at")[:5]
            return ProcessRunListSerializer(
                jobs, many=True, context={"request": None}
            ).data

        resolved_job_id = plan.arguments.get("job_id", job_id)
        if resolved_job_id is not None:
            try:
                resolved_job_id = int(resolved_job_id)
            except (TypeError, ValueError):
                resolved_job_id = None

        if plan.tool == "get_job_status":
            if resolved_job_id is None:
                return {"detail": "job_id is required"}
            job = ProcessRun.objects.prefetch_related("source_images__deposits").get(
                pk=resolved_job_id
            )
            return ProcessRunDetailSerializer(job, context={"request": None}).data

        if plan.tool == "get_job_logs":
            if resolved_job_id is None:
                return {"detail": "job_id is required"}
            job = ProcessRun.objects.get(pk=resolved_job_id)
            logs = job.extraction_logs.select_related("source_image").order_by(
                "sequence_index", "id"
            )
            return ExtractionLogSerializer(logs, many=True).data

        if plan.tool == "get_last_record_value":
            candidate_job = None
            if resolved_job_id is not None:
                candidate_job = (
                    ProcessRun.objects.prefetch_related(
                        "source_images__deposits", "deposits"
                    )
                    .filter(pk=resolved_job_id)
                    .first()
                )
            if candidate_job is None:
                candidate_job = (
                    ProcessRun.objects.prefetch_related(
                        "source_images__deposits", "deposits"
                    )
                    .filter(
                        status__in=[
                            ProcessRun.Status.COMPLETED,
                            ProcessRun.Status.COMPLETED_WITH_ERRORS,
                        ],
                        total_records__gt=0,
                    )
                    .order_by("-created_at")
                    .first()
                )
            if candidate_job is None:
                return {
                    "detail": "No hay jobs completados con registros para calcular el ultimo valor."
                }

            deposit = candidate_job.deposits.order_by("-sequence_index", "-id").first()
            if deposit is None:
                return {"detail": "El job seleccionado no tiene registros extraidos."}

            return {
                "job_id": candidate_job.id,
                "original_filename": candidate_job.original_filename,
                "status": candidate_job.status,
                "total_records": candidate_job.total_records,
                "last_record": {
                    "referencia": deposit.referencia,
                    "valor": str(deposit.valor),
                    "fecha_consignacion": deposit.fecha_consignacion,
                    "hora_consignacion": deposit.hora_consignacion,
                    "sequence_index": deposit.sequence_index,
                },
            }

        if plan.tool == "get_completed_records_summary":
            summary = ProcessRun.objects.filter(
                status__in=[
                    ProcessRun.Status.COMPLETED,
                    ProcessRun.Status.COMPLETED_WITH_ERRORS,
                ]
            ).aggregate(
                total_records=Count("deposits"),
                total_value=Sum("deposits__valor"),
                jobs_count=Count("id", distinct=True),
            )
            return {
                "jobs_count": int(summary.get("jobs_count") or 0),
                "total_records": int(summary.get("total_records") or 0),
                "total_value": str(summary.get("total_value") or Decimal("0")),
                "currency": "COP",
            }

        if plan.tool == "get_processing_settings":
            return ProcessingSettingsSerializer(
                get_or_create_processing_settings()
            ).data

        if plan.tool == "get_processing_settings_options":
            return available_options()

        if plan.tool == "update_processing_settings":
            if not _mutation_tools_enabled():
                return {
                    "detail": "update_processing_settings is disabled by server configuration."
                }
            instance = get_or_create_processing_settings()
            serializer = ProcessingSettingsSerializer(
                instance, data=plan.arguments, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return serializer.data

        if plan.tool == "process_job":
            if not _mutation_tools_enabled():
                return {"detail": "process_job is disabled by server configuration."}
            if resolved_job_id is None:
                return {"detail": "job_id is required"}
            job = ProcessRun.objects.get(pk=resolved_job_id)
            processed = process_job(job)
            processed = ProcessRun.objects.prefetch_related(
                "source_images__deposits"
            ).get(pk=processed.pk)
            return ProcessRunDetailSerializer(processed, context={"request": None}).data

        if plan.tool == "export_job_excel":
            if not _mutation_tools_enabled():
                return {
                    "detail": "export_job_excel is disabled by server configuration."
                }
            if resolved_job_id is None:
                return {"detail": "job_id is required"}
            job = ProcessRun.objects.get(pk=resolved_job_id)
            exported = export_job_to_excel(job)
            return ProcessRunDetailSerializer(exported, context={"request": None}).data

        if plan.tool == "upload_document":
            file_path = plan.arguments.get("file_path")
            if not isinstance(file_path, str) or not file_path.strip():
                return {"detail": "file_path is required"}
            try:
                return upload_document_from_path(file_path)
            except ValueError as exc:
                return {"detail": str(exc)}

        if plan.tool == "list_available_tools":
            return [
                {"tool": tool, "risk_level": get_tool_risk_level(tool)}
                for tool in sorted(tool for tool in _ALLOWED_TOOLS if tool != "none")
            ]

        if plan.tool in {"explain_capabilities", "help"}:
            return {
                "title": "Puedo ayudarte con esto",
                "capabilities": _CAPABILITIES,
                "tools": [
                    {"tool": tool, "risk_level": get_tool_risk_level(tool)}
                    for tool in sorted(
                        tool for tool in _ALLOWED_TOOLS if tool != "none"
                    )
                ],
            }

        return {"detail": f"Unsupported tool: {plan.tool}"}

    def _execute_crud_database(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            return {"detail": "crud_database requiere arguments como objeto."}

        operation = str(arguments.get("operation") or "").strip().lower()
        source = str(arguments.get("source") or "").strip()
        if operation not in {"create", "read", "update", "delete"}:
            return {"detail": "operation invalida. Usa create, read, update o delete."}
        if source not in _QUERY_SOURCES:
            return {
                "detail": "source invalido. Usa process_runs, deposits, source_images o logs.",
                "available_sources": list(_QUERY_SOURCES.keys()),
            }

        model = _QUERY_SOURCES[source]["model"]
        allowed_fields = _QUERY_SOURCES[source]["fields"]

        if operation == "read":
            query = arguments.get("query")
            if isinstance(query, dict):
                return self._execute_query_database(query)
            query_from_filters = {
                "source": source,
                "select": [
                    field for field in ("id", "created_at") if field in allowed_fields
                ],
                "filters": (
                    arguments.get("filters")
                    if isinstance(arguments.get("filters"), list)
                    else []
                ),
                "order_by": (
                    arguments.get("order_by")
                    if isinstance(arguments.get("order_by"), list)
                    else []
                ),
                "limit": arguments.get("limit", 30),
            }
            return self._execute_query_database(query_from_filters)

        if operation == "create":
            values = (
                arguments.get("values")
                if isinstance(arguments.get("values"), dict)
                else {}
            )
            if not values:
                return {
                    "detail": "create requiere arguments.values con campos a crear."
                }
            writable = self._model_writable_fields(model)
            payload = {k: v for k, v in values.items() if k in writable}
            if not payload:
                return {"detail": "No hay campos validos para crear el registro."}
            try:
                instance = model.objects.create(**payload)
                return {
                    "operation": "create",
                    "source": source,
                    "created_id": instance.pk,
                    "data": self._serialize_model_instance(instance, allowed_fields),
                }
            except Exception as exc:
                return {
                    "detail": "No fue posible crear el registro.",
                    "meta": {"error": exc.__class__.__name__, "message": str(exc)},
                }

        queryset = model.objects.all()
        filters = (
            arguments.get("filters")
            if isinstance(arguments.get("filters"), list)
            else []
        )
        filtered, warnings = self._apply_crud_filters(queryset, filters, allowed_fields)

        if operation == "update":
            values = (
                arguments.get("values")
                if isinstance(arguments.get("values"), dict)
                else {}
            )
            if not values:
                return {
                    "detail": "update requiere arguments.values con campos a actualizar."
                }
            writable = self._model_writable_fields(model)
            payload = {k: v for k, v in values.items() if k in writable}
            if not payload:
                return {"detail": "No hay campos validos para actualizar el registro."}
            try:
                updated_count = filtered.update(**payload)
                return {
                    "operation": "update",
                    "source": source,
                    "updated_count": int(updated_count),
                    "warnings": warnings,
                }
            except Exception as exc:
                return {
                    "detail": "No fue posible actualizar registros.",
                    "meta": {"error": exc.__class__.__name__, "message": str(exc)},
                }

        try:
            deleted_count, _ = filtered.delete()
            return {
                "operation": "delete",
                "source": source,
                "deleted_count": int(deleted_count),
                "warnings": warnings,
            }
        except Exception as exc:
            return {
                "detail": "No fue posible eliminar registros.",
                "meta": {"error": exc.__class__.__name__, "message": str(exc)},
            }

    def _model_writable_fields(self, model: Any) -> set[str]:
        blocked = {"id", "created_at", "updated_at"}
        writable: set[str] = set()
        for field in model._meta.concrete_fields:
            if field.auto_created:
                continue
            if field.name in blocked:
                continue
            writable.add(field.name)
            if hasattr(field, "attname") and field.attname not in blocked:
                writable.add(field.attname)
        return writable

    def _serialize_model_instance(
        self, instance: Any, allowed_fields: set[str]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": instance.pk}
        for field in sorted(allowed_fields):
            if "__" in field:
                continue
            try:
                payload[field] = _to_json_safe(getattr(instance, field))
            except Exception:
                continue
        return payload

    def _apply_crud_filters(
        self, queryset: Any, filters: list[dict[str, Any]], allowed_fields: set[str]
    ) -> tuple[Any, list[str]]:
        warnings: list[str] = []
        for item in filters:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            op = str(item.get("op") or "eq").strip()
            value = item.get("value")
            if field not in allowed_fields:
                warnings.append(f"Filtro omitido: campo no permitido '{field}'.")
                continue
            try:
                if op == "eq":
                    queryset = queryset.filter(**{field: value})
                elif op == "ne":
                    queryset = queryset.exclude(**{field: value})
                elif op == "in" and isinstance(value, list):
                    queryset = queryset.filter(**{f"{field}__in": value})
                elif op == "gt":
                    queryset = queryset.filter(**{f"{field}__gt": value})
                elif op == "gte":
                    queryset = queryset.filter(**{f"{field}__gte": value})
                elif op == "lt":
                    queryset = queryset.filter(**{f"{field}__lt": value})
                elif op == "lte":
                    queryset = queryset.filter(**{f"{field}__lte": value})
                elif op == "contains" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__contains": value})
                elif op == "icontains" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__icontains": value})
                elif op == "isnull":
                    queryset = queryset.filter(**{f"{field}__isnull": bool(value)})
                elif op in {"date_eq", "date_gte", "date_lte"}:
                    parsed = self._parse_date_value(value)
                    if parsed is None:
                        warnings.append(
                            f"Filtro omitido: fecha invalida para '{field}'."
                        )
                        continue
                    lookup = {
                        "date_eq": f"{field}__date",
                        "date_gte": f"{field}__date__gte",
                        "date_lte": f"{field}__date__lte",
                    }[op]
                    queryset = queryset.filter(**{lookup: parsed})
                elif op == "in_last_days":
                    days = int(value)
                    cutoff = timezone.now() - timedelta(days=max(0, min(days, 3650)))
                    queryset = queryset.filter(**{f"{field}__gte": cutoff})
                else:
                    warnings.append(f"Filtro omitido: operador no soportado '{op}'.")
            except Exception as exc:
                warnings.append(
                    f"Filtro omitido por error '{exc.__class__.__name__}' en '{field}'."
                )
        return queryset, warnings

    def _execute_query_database(self, query: Any) -> dict[str, Any]:
        if not isinstance(query, dict):
            return {"detail": "query_database requiere arguments.query como objeto."}

        source = str(query.get("source") or "").strip()
        source_config = _QUERY_SOURCES.get(source)
        if source_config is None:
            return {
                "detail": "source invalido. Usa process_runs, deposits, source_images o logs.",
                "available_sources": list(_QUERY_SOURCES.keys()),
            }

        model = source_config["model"]
        allowed_fields: set[str] = source_config["fields"]
        queryset = model.objects.all()
        warnings: list[str] = []

        # Filters
        filters = query.get("filters") if isinstance(query.get("filters"), list) else []
        for item in filters:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            op = str(item.get("op") or "eq").strip()
            value = item.get("value")
            if field not in allowed_fields:
                warnings.append(f"Filtro omitido: campo no permitido '{field}'.")
                continue

            try:
                if op == "eq":
                    queryset = queryset.filter(**{field: value})
                elif op == "ne":
                    queryset = queryset.exclude(**{field: value})
                elif op == "in" and isinstance(value, list):
                    queryset = queryset.filter(**{f"{field}__in": value})
                elif op == "not_in" and isinstance(value, list):
                    queryset = queryset.exclude(**{f"{field}__in": value})
                elif op == "gt":
                    queryset = queryset.filter(**{f"{field}__gt": value})
                elif op == "gte":
                    queryset = queryset.filter(**{f"{field}__gte": value})
                elif op == "lt":
                    queryset = queryset.filter(**{f"{field}__lt": value})
                elif op == "lte":
                    queryset = queryset.filter(**{f"{field}__lte": value})
                elif op == "between" and isinstance(value, list) and len(value) == 2:
                    queryset = queryset.filter(
                        **{f"{field}__range": [value[0], value[1]]}
                    )
                elif op == "contains" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__contains": value})
                elif op == "icontains" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__icontains": value})
                elif op == "startswith" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__startswith": value})
                elif op == "istartswith" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__istartswith": value})
                elif op == "endswith" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__endswith": value})
                elif op == "iendswith" and isinstance(value, str):
                    queryset = queryset.filter(**{f"{field}__iendswith": value})
                elif op == "isnull":
                    queryset = queryset.filter(**{f"{field}__isnull": bool(value)})
                elif op in {"date_eq", "date_gte", "date_lte"}:
                    parsed_date = self._parse_date_value(value)
                    if parsed_date is None:
                        warnings.append(
                            f"Filtro omitido: valor de fecha invalido para '{field}' con op '{op}'."
                        )
                        continue
                    lookup = {
                        "date_eq": f"{field}__date",
                        "date_gte": f"{field}__date__gte",
                        "date_lte": f"{field}__date__lte",
                    }[op]
                    queryset = queryset.filter(**{lookup: parsed_date})
                elif op == "in_last_days":
                    try:
                        days = int(value)
                    except (TypeError, ValueError):
                        warnings.append(
                            f"Filtro omitido: in_last_days requiere entero para '{field}'."
                        )
                        continue
                    days = max(0, min(days, 3650))
                    cutoff = timezone.now() - timedelta(days=days)
                    queryset = queryset.filter(**{f"{field}__gte": cutoff})
                else:
                    warnings.append(
                        f"Filtro omitido: operador no soportado '{op}' para campo '{field}'."
                    )
            except Exception as exc:
                warnings.append(
                    f"Filtro omitido: error aplicando op '{op}' en campo '{field}' ({exc.__class__.__name__})."
                )

        # Aggregations
        aggregations = (
            query.get("aggregations")
            if isinstance(query.get("aggregations"), list)
            else []
        )
        aggregate_expressions: dict[str, Any] = {}
        for item in aggregations:
            if not isinstance(item, dict):
                continue
            agg_type = str(item.get("type") or "").strip()
            field = str(item.get("field") or "id").strip()
            alias = str(item.get("as") or "").strip()
            if field not in allowed_fields:
                warnings.append(f"Agregacion omitida: campo no permitido '{field}'.")
                continue
            if not alias:
                alias = f"{agg_type}_{field}".replace("__", "_")

            if agg_type == "count":
                aggregate_expressions[alias] = Count(field)
            elif agg_type == "distinct_count":
                aggregate_expressions[alias] = Count(field, distinct=True)
            elif agg_type == "sum":
                aggregate_expressions[alias] = Sum(field)
            elif agg_type == "avg":
                aggregate_expressions[alias] = Avg(field)
            elif agg_type == "min":
                aggregate_expressions[alias] = Min(field)
            elif agg_type == "max":
                aggregate_expressions[alias] = Max(field)
            else:
                warnings.append(f"Agregacion omitida: tipo no soportado '{agg_type}'.")

        # Group by
        group_by_raw = (
            query.get("group_by") if isinstance(query.get("group_by"), list) else []
        )
        group_by = [
            str(field).strip()
            for field in group_by_raw
            if str(field).strip() in allowed_fields
        ]
        if isinstance(query.get("group_by"), list):
            for raw_field in query.get("group_by") or []:
                normalized = str(raw_field).strip()
                if normalized and normalized not in allowed_fields:
                    warnings.append(
                        f"group_by omitido: campo no permitido '{normalized}'."
                    )

        # Select and limit
        select_raw = (
            query.get("select") if isinstance(query.get("select"), list) else []
        )
        select_fields = [
            str(field).strip()
            for field in select_raw
            if str(field).strip() in allowed_fields
        ]
        for raw_field in select_raw:
            normalized = str(raw_field).strip()
            if normalized and normalized not in allowed_fields:
                warnings.append(f"select omitido: campo no permitido '{normalized}'.")
        if not select_fields and not aggregate_expressions:
            select_fields = [
                field for field in ("id", "created_at") if field in allowed_fields
            ]
            if source == "process_runs":
                select_fields = [
                    field
                    for field in (
                        "id",
                        "original_filename",
                        "status",
                        "total_records",
                        "created_at",
                    )
                    if field in allowed_fields
                ]

        try:
            limit = int(query.get("limit", 30))
        except (TypeError, ValueError):
            limit = 30
        limit = max(1, min(limit, 200))

        # Order by
        order_by_raw = (
            query.get("order_by") if isinstance(query.get("order_by"), list) else []
        )
        order_by_fields: list[str] = []
        orderable_fields = set(allowed_fields)
        orderable_fields.update(aggregate_expressions.keys())
        orderable_fields.add("rows_count")
        for item in order_by_raw:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            direction = str(item.get("direction") or "asc").strip().lower()
            if field not in orderable_fields:
                warnings.append(f"order_by omitido: campo no permitido '{field}'.")
                continue
            order_by_fields.append(f"-{field}" if direction == "desc" else field)

        rows: list[dict[str, Any]]
        try:
            if group_by:
                grouped = queryset.values(*group_by)
                if aggregate_expressions:
                    grouped = grouped.annotate(**aggregate_expressions)
                else:
                    grouped = grouped.annotate(rows_count=Count("id"))
                if order_by_fields:
                    grouped = grouped.order_by(*order_by_fields)
                rows = list(grouped[:limit])
            elif aggregate_expressions:
                rows = [queryset.aggregate(**aggregate_expressions)]
            else:
                selected = queryset.values(*select_fields)
                if order_by_fields:
                    selected = selected.order_by(*order_by_fields)
                rows = list(selected[:limit])
        except Exception as exc:
            return {
                "detail": "No fue posible ejecutar la consulta con los criterios solicitados.",
                "meta": {
                    "warnings": [
                        *warnings,
                        f"Error de ejecucion: {exc.__class__.__name__}.",
                    ]
                },
            }

        return {
            "source": source,
            "rows": _to_json_safe(rows),
            "meta": {
                "rows_count": len(rows),
                "limit": limit,
                "group_by": group_by,
                "has_aggregations": bool(aggregate_expressions),
                "warnings": warnings,
            },
        }

    def _describe_database_schema(self) -> dict[str, Any]:
        sources: dict[str, Any] = {}
        for source_name, config in _QUERY_SOURCES.items():
            fields = sorted(config["fields"])
            sources[source_name] = {
                "fields": fields,
                "sample_query": {
                    "source": source_name,
                    "select": fields[: min(4, len(fields))],
                    "filters": [],
                    "order_by": (
                        [{"field": fields[0], "direction": "desc"}] if fields else []
                    ),
                    "limit": 20,
                },
            }

        return {
            "sources": sources,
            "sql_tables": self._sql_tables_catalog(),
            "supported_filter_ops": _SUPPORTED_FILTER_OPS,
            "supported_aggregations": _SUPPORTED_AGGREGATIONS,
            "limits": {"default": 30, "max": 200},
        }

    def _sql_tables_catalog(self) -> dict[str, Any]:
        return {
            ProcessRun._meta.db_table: sorted(_QUERY_SOURCES["process_runs"]["fields"]),
            ExtractedDeposit._meta.db_table: sorted(
                _QUERY_SOURCES["deposits"]["fields"]
            ),
            SourceImage._meta.db_table: sorted(
                _QUERY_SOURCES["source_images"]["fields"]
            ),
            ExtractionLog._meta.db_table: sorted(_QUERY_SOURCES["logs"]["fields"]),
        }

    def _execute_query_database_sql(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            return {"detail": "query_database_sql requiere arguments como objeto."}

        sql = str(arguments.get("sql") or "").strip()
        if not sql:
            return {"detail": "query_database_sql requiere arguments.sql."}

        try:
            limit = int(arguments.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, limit)

        if not _allow_unsafe_sql_enabled():
            validation_error = self._validate_readonly_sql(sql)
            if validation_error:
                return {"detail": validation_error}

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                description = cursor.description or []
                if description:
                    columns = [col[0] for col in description]
                    raw_rows = cursor.fetchmany(limit)
                else:
                    columns = []
                    raw_rows = []
                    affected = cursor.rowcount

            rows = [
                {columns[idx]: _to_json_safe(value) for idx, value in enumerate(row)}
                for row in raw_rows
            ]

            response = {
                "sql": sql,
                "rows": rows,
                "meta": {
                    "rows_count": len(rows),
                    "limit": limit,
                    "columns": columns,
                    "unsafe_sql_enabled": _allow_unsafe_sql_enabled(),
                },
            }
            if not columns:
                response["meta"]["rows_affected"] = affected
            return response
        except Exception as exc:
            return {
                "detail": "No fue posible ejecutar la sentencia SQL solicitada.",
                "meta": {
                    "error": exc.__class__.__name__,
                    "unsafe_sql_enabled": _allow_unsafe_sql_enabled(),
                },
            }

    def _validate_readonly_sql(self, sql: str) -> str | None:
        stripped = sql.strip().rstrip(";")
        normalized = stripped.lower()

        if not normalized.startswith("select") and not normalized.startswith("with"):
            return (
                "Solo se permiten consultas SQL de lectura (SELECT o WITH ... SELECT)."
            )

        if ";" in stripped:
            return "No se permiten multiples sentencias SQL en una sola consulta."

        forbidden_patterns = [
            r"\binsert\b",
            r"\bupdate\b",
            r"\bdelete\b",
            r"\bdrop\b",
            r"\balter\b",
            r"\btruncate\b",
            r"\bcreate\b",
            r"\breplace\b",
            r"\bpragma\b",
            r"\battach\b",
            r"\bdetach\b",
            r"\bvacuum\b",
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, normalized):
                return (
                    "La sentencia contiene operaciones no permitidas para modo lectura."
                )

        return None

    def _parse_date_value(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None

        text = value.strip().lower()
        today = timezone.localdate()
        if text == "today":
            return today
        if text == "yesterday":
            return today - timedelta(days=1)

        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                return None
        return None


class ResponseAgent:
    def __init__(
        self,
        model: str,
        timeout: int,
        provider: str,
        api_key: str = "",
        temperature: float = 0.2,
        num_predict: int = 256,
        text_client: AssistantTextClient | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.provider = provider
        self.api_key = api_key
        self.temperature = temperature
        self.num_predict = num_predict
        self.text_client = text_client or AssistantTextClient()

    def _last_user_message(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return (message.get("content") or "").strip().lower()
        return ""

    def compose(
        self,
        messages: list[dict[str, str]],
        intent: AssistantIntent,
        plan: AssistantPlan,
        tool_payload: Any,
        job_id: int | None,
        errors: int,
        task: AssistantTask | None = None,
        task_context: dict[str, Any] | None = None,
    ) -> str:
        if task is not None and task_context is not None:
            if task.name == "explain_job_summary" and isinstance(tool_payload, dict):
                detail = tool_payload.get("detail")
                if detail:
                    return str(detail)
                total_records = tool_payload.get("total_records", 0)
                total_images = tool_payload.get("total_images", 0)
                status = tool_payload.get("status", "unknown")
                return f"El job #{job_id} va en estado {status}, con {total_images} imagen(es) y {total_records} registro(s) extraidos."

            if task.name == "explain_job_findings" and isinstance(tool_payload, dict):
                findings = (
                    task_context.get("findings", {})
                    if isinstance(task_context, dict)
                    else {}
                )
                if isinstance(findings, dict):
                    count = findings.get("rows_with_observations", 0)
                    return (
                        f"Encontré {count} fila(s) con hallazgos en el job #{job_id}."
                    )

            if task.name == "explain_row_issue" and isinstance(task_context, dict):
                selected_row = task_context.get("selected_row")
                if isinstance(selected_row, dict):
                    return (
                        f"La fila seleccionada tiene referencia {selected_row.get('referencia', 'N/D')} "
                        f"y valor {selected_row.get('valor', 'N/D')}. "
                        "Te muestro su contexto para revisar el problema."
                    )

            if task.name == "suggest_row_correction" and isinstance(task_context, dict):
                selected_row = task_context.get("selected_row")
                if isinstance(selected_row, dict):
                    observations = selected_row.get("observations") or []
                    suggestion = "Revisa la fila seleccionada y confirma los datos faltantes o inconsistentes."
                    if observations:
                        suggestion = f"Revisa la fila seleccionada. Observaciones detectadas: {', '.join(str(item) for item in observations[:3])}."
                    return suggestion

            if task.name == "summarize_extraction_logs" and isinstance(
                tool_payload, list
            ):
                if tool_payload:
                    errors_count = sum(
                        1
                        for item in tool_payload
                        if isinstance(item, dict) and item.get("is_error")
                    )
                    return f"Encontré {len(tool_payload)} log(s) para el job #{job_id}; {errors_count} indican error."

            if task.name == "explain_extraction_criteria" and isinstance(
                task_context, dict
            ):
                criteria = task_context.get("criteria", {})
                if isinstance(criteria, dict):
                    enabled = criteria.get("enabled_fields") or []
                    if enabled:
                        return (
                            "Los criterios activos incluyen: "
                            + ", ".join(str(item) for item in enabled)
                            + "."
                        )

            if task.name == "prepare_export":
                return "Puedo preparar la exportación, pero necesito tu confirmación antes de ejecutarla."

            if task.name == "prepare_reprocess":
                return "Puedo reprocesar el job, pero necesito tu confirmación antes de ejecutarlo."

        if intent.name == "followup_not_supported":
            return (
                "No puedo hacer eso con esa instruccion ambigua. "
                "Por favor especifica de nuevo la consulta completa."
            )

        if plan.tool == "crud_database" and isinstance(tool_payload, dict):
            if tool_payload.get("detail"):
                return str(tool_payload.get("detail"))
            operation = tool_payload.get("operation")
            if operation == "create":
                return f"Registro creado correctamente con id {tool_payload.get('created_id')}."
            if operation == "update":
                return f"Actualicé {tool_payload.get('updated_count', 0)} registro(s)."
            if operation == "delete":
                return f"Eliminé {tool_payload.get('deleted_count', 0)} registro(s)."
            if operation == "read":
                return "Consulta CRUD de lectura ejecutada correctamente."

        if plan.tool == "explain_capabilities" and isinstance(tool_payload, dict):
            capabilities = tool_payload.get("capabilities") or []
            if isinstance(capabilities, list) and capabilities:
                return "Puedo ayudarte con: " + "; ".join(
                    str(item) for item in capabilities
                )
            return (
                "Puedo ayudarte con jobs, logs, correcciones, settings y exportación."
            )

        if plan.tool == "help" and isinstance(tool_payload, dict):
            return self.compose(
                messages=messages,
                intent=intent,
                plan=AssistantPlan(
                    tool="explain_capabilities",
                    arguments={},
                    intent_name=plan.intent_name,
                    intent_summary=plan.intent_summary,
                ),
                tool_payload=tool_payload,
                job_id=job_id,
                errors=errors,
            )

        if plan.tool == "list_jobs" and isinstance(tool_payload, list):
            return f"Encontré {len(tool_payload)} jobs recientes. Te los muestro en tarjetas en la interfaz."

        if plan.tool == "list_available_tools" and isinstance(tool_payload, list):
            tools = [
                item.get("tool", str(item))
                for item in tool_payload
                if isinstance(item, dict)
            ]
            if tools:
                return "Estas son las herramientas disponibles: " + ", ".join(tools)
            return "Estas son las herramientas disponibles."

        if plan.tool == "describe_database_schema" and isinstance(tool_payload, dict):
            sources = (
                tool_payload.get("sources")
                if isinstance(tool_payload.get("sources"), dict)
                else {}
            )
            return (
                f"Puedo consultar {len(sources)} fuentes de datos. "
                "Te muestro tablas/campos disponibles y ejemplo de consulta para cada una."
            )

        if plan.tool == "query_database" and isinstance(tool_payload, dict):
            detail = tool_payload.get("detail")
            if detail:
                return str(detail)
            source = tool_payload.get("source", "datos")
            meta = tool_payload.get("meta") or {}
            rows = tool_payload.get("rows", [])

            # Special handling for count aggregations
            if meta.get("has_aggregations") and len(rows) == 1:
                row = rows[0]
                if "total_records" in row:
                    count = row["total_records"]
                    return f"Actualmente hay {count} registros en total."

            rows_count = meta.get("rows_count", 0)
            return f"Ejecuté una consulta sobre {source} y obtuve {rows_count} resultado(s)."

        if plan.tool == "query_database_sql" and isinstance(tool_payload, dict):
            detail = tool_payload.get("detail")
            if detail:
                return str(detail)
            meta = tool_payload.get("meta") or {}
            rows_count = meta.get("rows_count", 0)
            return f"Ejecuté la sentencia SQL en modo lectura y obtuve {rows_count} resultado(s)."

        if isinstance(tool_payload, dict) and tool_payload.get("requires_confirmation"):
            detail = tool_payload.get("detail")
            if detail:
                return str(detail)
            return "La accion solicitada requiere confirmacion explicita."

        if plan.tool == "get_completed_records_summary" and isinstance(
            tool_payload, dict
        ):
            detail = tool_payload.get("detail")
            if detail:
                return str(detail)
            return (
                f"El total acumulado de {tool_payload.get('total_records', 0)} registros completados "
                f"es {tool_payload.get('total_value', '0.00')} {tool_payload.get('currency', '')}."
            )

        if plan.tool == "get_last_record_value" and isinstance(tool_payload, dict):
            detail = tool_payload.get("detail")
            if detail:
                return str(detail)
            last_record = tool_payload.get("last_record") or {}
            valor = last_record.get("valor") or "N/D"
            referencia = last_record.get("referencia") or "N/D"
            job_ref = tool_payload.get("job_id")
            return f"El ultimo registro del job #{job_ref} tiene valor {valor} y referencia {referencia}."

        if plan.tool == "update_deposit_correction" and isinstance(tool_payload, dict):
            detail = deposit_correction_failure_description(tool_payload)
            if detail and tool_payload.get("operation") != "update":
                return detail
            return deposit_correction_success_description(tool_payload)

        if plan.tool == "none":
            return self._general_chat_response(
                messages=messages,
                job_id=job_id,
                errors=errors,
                query_context=task_context or {},
                task=task,
                task_context=task_context or {},
            )

        conversation = self._last_user_message(messages)
        prompt = f"""
Eres el asistente del dashboard de procesamiento.
Responde en espanol, claro y breve.

Contexto:
- intent_detectado: {intent.name}
- resumen_intencion: {intent.summary}
- job_id_actual: {job_id if job_id is not None else 'null'}
- errores_detectados: {errors}
- herramienta_ejecutada: {plan.tool}

Conversacion:
{conversation}

Resultado de la herramienta:
{self._safe_json_dump(tool_payload)}

Instrucciones:
- Si la herramienta devolvio datos, resumelos de forma util.
- Si no se uso herramienta, responde directamente a la pregunta.
- No menciones JSON ni detalles internos de implementacion.
- Si la herramienta ejecutada es get_job_status, resume estado, total de registros y nombre del archivo.
- Si la herramienta ejecutada es get_job_logs, resume la cantidad de logs y el estado general.
""".strip()

        if task is not None and task_context is not None:
            prompt += f"\n\nTarea orientada:\n- {task.name}\n- {task.summary}\n\nContexto de tarea:\n{self._safe_json_dump(task_context)}"
        response = self._generate_text(prompt)
        return response.strip() or "No pude generar una respuesta en este momento."

    def _generate_text(self, prompt: str) -> str:
        return self.text_client.generate(
            prompt,
            TextGenerationConfig(
                provider=self.provider,
                model=self.model,
                timeout=self.timeout,
                api_key=self.api_key,
                temperature=self.temperature,
                num_predict=self.num_predict,
            ),
        )

    def _format_conversation(self, messages: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for message in messages[-8:]:
            role = message.get("role", "user")
            content = (message.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _safe_json_dump(self, payload: Any) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            return json.dumps(str(payload), ensure_ascii=False, indent=2)

    def _general_chat_response(
        self,
        messages: list[dict[str, str]],
        job_id: int | None,
        errors: int,
        query_context: dict[str, Any],
        task: AssistantTask | None = None,
        task_context: dict[str, Any] | None = None,
    ) -> str:
        conversation = self._format_conversation(messages)
        context_hint = self._format_context_hint(query_context)
        prompt = f"""
Eres un asistente conversacional útil para un dashboard de procesamiento.
Responde de forma natural, breve y clara en espanol.

        Contexto:
        - job_id_actual: {job_id if job_id is not None else 'null'}
        - errores_detectados: {errors}
        - contexto_activo: {context_hint}
        - query_context: {self._safe_json_dump(query_context)}
        - tarea_actual: {task.name if task else 'answer_general_question'}
        - task_context: {self._safe_json_dump(task_context or {})}

Capacidades:
{chr(10).join(f"- {item}" for item in _CAPABILITIES)}

Conversacion:
{conversation}

Instrucciones:
- Si el usuario saluda, saluda de vuelta y ofrece ayuda.
- Si pregunta por herramientas o MCP, explica capacidades sin listar JSON.
- Si pide ayuda general, responde como conversación.
""".strip()
        response = self._generate_text(prompt)
        return (
            response.strip()
            or "Hola, puedo ayudarte con jobs, logs, correcciones, settings y exportación."
        )

    def _format_context_hint(self, query_context: dict[str, Any]) -> str:
        if not query_context:
            return "sin contexto activo"
        scope = (
            query_context.get("contextScope") or query_context.get("page") or "general"
        )
        parts = [f"scope={scope}"]
        for key in (
            "jobId",
            "selectedRowId",
            "selectedField",
            "depositId",
            "sourceImageId",
            "currentImageId",
        ):
            if key in query_context and query_context.get(key) is not None:
                parts.append(f"{key}={query_context.get(key)}")
        visible = query_context.get("visibleIssueIds")
        if isinstance(visible, list) and visible:
            parts.append(f"visibleIssueIds={visible[:8]}")
        return ", ".join(parts)


class AssistantAgent:
    def __init__(self) -> None:
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.provider = "ollama"
        self.api_key = ""
        self.temperature = 0.2
        self.num_predict = 256
        self.intent_agent = IntentAgent(
            self.model, self.timeout, self.provider, self.api_key
        )
        self.planner_agent = PlanningAgent(
            self.model, self.timeout, self.provider, self.api_key
        )
        self.tool_agent = ToolExecutionAgent()
        self.response_agent = ResponseAgent(
            self.model,
            self.timeout,
            self.provider,
            self.api_key,
            temperature=self.temperature,
            num_predict=self.num_predict,
        )

    def _sync_runtime_model(self) -> None:
        runtime = get_runtime_config()
        model = runtime.assistant_model or runtime.llm_model or settings.OLLAMA_MODEL
        timeout = runtime.request_timeout_seconds or settings.OLLAMA_TIMEOUT
        provider = runtime.assistant_provider or runtime.llm_provider or "ollama"
        api_key = runtime.assistant_api_key or runtime.llm_api_key or ""

        self.model = model
        self.timeout = timeout
        self.provider = provider
        self.api_key = api_key
        self.temperature = runtime.assistant_temperature or 0.2
        self.num_predict = runtime.assistant_num_predict or 256

        self.intent_agent.model = model
        self.intent_agent.timeout = timeout
        self.intent_agent.provider = provider
        self.intent_agent.api_key = api_key
        self.planner_agent.model = model
        self.planner_agent.timeout = timeout
        self.planner_agent.provider = provider
        self.planner_agent.api_key = api_key
        self.response_agent.model = model
        self.response_agent.timeout = timeout
        self.response_agent.provider = provider
        self.response_agent.api_key = api_key
        self.response_agent.model = model
        self.response_agent.temperature = self.temperature
        self.response_agent.num_predict = self.num_predict

    def answer(
        self,
        messages: list[dict[str, str]],
        job_id: int | None = None,
        errors: int = 0,
        query_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_query_context = _normalize_query_context(query_context)
        request_id = (
            str(
                normalized_query_context.get("request_id")
                or normalized_query_context.get("requestId")
                or ""
            ).strip()
            or "n/a"
        )
        try:
            self._sync_runtime_model()
            pending_action = self._extract_pending_action(normalized_query_context)
            last_user_message = self._last_user_message(messages)

            if pending_action is not None:
                pending_action, pending_error = normalize_pending_action(pending_action)
                if pending_error is not None:
                    return self._clarification_response(
                        pending_error,
                        normalized_query_context,
                    )
                if self._is_confirmation_message(last_user_message):
                    revalidation_error = validate_pending_action(
                        pending_action,
                        job_id=job_id or pending_action.get("job_id"),
                    )
                    if revalidation_error is not None:
                        return self._clarification_response(
                            revalidation_error,
                            normalized_query_context,
                        )
                    pending_plan = self._plan_from_pending_action(pending_action)
                    tool_payload = self.tool_agent.execute(
                        pending_plan, job_id=job_id or pending_action.get("job_id")
                    )
                    reply = self.response_agent.compose(
                        messages,
                        AssistantIntent(
                            name="confirmation",
                            confidence=1.0,
                            summary="Accion confirmada por el usuario",
                        ),
                        pending_plan,
                        tool_payload,
                        job_id=job_id or pending_action.get("job_id"),
                        errors=errors,
                        task=None,
                        task_context=None,
                    )
                    return {
                        "reply": reply,
                        "message": reply,
                        "tool": pending_plan.tool,
                        "data": tool_payload,
                        "task": "confirmation_executed",
                        "task_context": {},
                        "query_context": clear_pending_action(normalized_query_context),
                    }
                if self._is_cancel_message(last_user_message):
                    reply = "De acuerdo, cancelé la acción pendiente."
                    return {
                        "reply": reply,
                        "message": reply,
                        "tool": "none",
                        "data": {
                            "detail": "pending_action_cancelled",
                            "pending_action": pending_action,
                        },
                        "task": "confirmation_cancelled",
                        "task_context": {},
                        "query_context": clear_pending_action(normalized_query_context),
                    }

            intent = self.intent_agent.infer(
                messages,
                job_id=job_id,
                errors=errors,
            )
            plan = self.planner_agent.plan(
                intent,
                messages,
                job_id=job_id,
                errors=errors,
            )
            last_user_message = ""
            for message in reversed(messages):
                if message.get("role") == "user":
                    last_user_message = message.get("content") or ""
                    break
            task = resolve_assistant_task(
                user_message=last_user_message,
                job_id=job_id,
                query_context=normalized_query_context,
                tool=plan.tool,
            )
            task_context = build_assistant_task_context(
                task=task,
                job_id=job_id,
                query_context=normalized_query_context,
            )
            if plan.tool == "update_deposit_correction":
                clarification = deposit_correction_needs_clarification(
                    plan.arguments if isinstance(plan.arguments, dict) else {},
                    job_id,
                )
                if clarification is not None:
                    return self._clarification_response(
                        clarification,
                        normalized_query_context,
                        task=task,
                        task_context=task_context,
                    )
            if tool_requires_confirmation(plan.tool):
                pending_context = dict(normalized_query_context)
                if plan.tool == "update_deposit_correction":
                    confirmation_arguments = (
                        deposit_correction_payload_for_correction(plan.arguments)
                        if isinstance(plan.arguments, dict)
                        else {}
                    )
                    confirmation_reply = deposit_correction_confirmation_message(
                        confirmation_arguments
                    )
                    confirmation_summary = deposit_correction_summary(
                        confirmation_arguments
                    )
                else:
                    confirmation_arguments = (
                        plan.arguments if isinstance(plan.arguments, dict) else {}
                    )
                    confirmation_reply = confirmation_message(
                        plan.tool, confirmation_arguments
                    )
                    confirmation_summary = plan.intent_summary
                pending_context["pending_action"] = build_pending_action(
                    tool=plan.tool,
                    arguments=confirmation_arguments,
                    intent_name=plan.intent_name,
                    intent_summary=confirmation_summary,
                    job_id=job_id,
                )
                return {
                    "reply": confirmation_reply,
                    "message": confirmation_reply,
                    "tool": plan.tool,
                    "data": {
                        "detail": confirmation_reply,
                        "requires_confirmation": True,
                        "risk_level": get_tool_risk_level(plan.tool),
                        "arguments": confirmation_arguments,
                    },
                    "task": task.name,
                    "task_context": task_context,
                    "query_context": pending_context,
                }
            tool_payload = self.tool_agent.execute(plan, job_id=job_id)
            reply = self.response_agent.compose(
                messages,
                intent,
                plan,
                tool_payload,
                job_id=job_id,
                errors=errors,
                task=task,
                task_context=task_context,
            )
            return {
                "reply": reply,
                "message": reply,
                "tool": plan.tool,
                "data": tool_payload,
                "task": task.name,
                "task_context": task_context,
                "query_context": clear_pending_action(normalized_query_context),
            }
        except AssistantProviderError as exc:
            logger.warning(
                "Assistant provider error during answer pipeline: provider=%s model=%s request_id=%s stage=answer status=%s code=%s detail=%s",
                exc.provider,
                self.model,
                request_id,
                exc.status_code,
                exc.code,
                exc.detail,
            )
            reply = (
                _assistant_memory_recommendation()
                if exc.code == "assistant_model_too_large"
                else "El asistente no esta disponible temporalmente. Hubo un problema con el proveedor de texto."
            )
            return {
                "reply": reply,
                "message": reply,
                "tool": "none",
                "data": {
                    "detail": exc.code,
                    "provider": exc.provider,
                    "status_code": exc.status_code,
                    "error": exc.detail,
                },
                "debug": {
                    "intent": None,
                    "confidence": None,
                    "selected_tool": "none",
                    "fallback_used": True,
                    "errors": [f"{exc.provider}:{exc.code}:{exc.detail}"],
                },
                "query_context": clear_pending_action(normalized_query_context),
            }
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.warning(
                "Assistant agent unavailable during answer pipeline: model=%s request_id=%s stage=answer error=%s: %s",
                self.model,
                request_id,
                exc.__class__.__name__,
                exc,
            )
            return {
                "reply": (
                    "El asistente no esta disponible temporalmente. "
                    "Verifica la configuracion del proveedor LLM e intenta de nuevo."
                ),
                "message": (
                    "El asistente no esta disponible temporalmente. "
                    "Verifica la configuracion del proveedor LLM e intenta de nuevo."
                ),
                "tool": "none",
                "data": {
                    "detail": "assistant_unavailable",
                    "error": str(exc),
                },
                "debug": {
                    "intent": None,
                    "confidence": None,
                    "selected_tool": "none",
                    "fallback_used": True,
                    "errors": [f"{exc.__class__.__name__}: {exc}"],
                },
                "query_context": clear_pending_action(normalized_query_context),
            }

    def _last_user_message(self, messages: list[dict[str, str]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return (message.get("content") or "").strip().lower()
        return ""

    def _is_confirmation_message(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in _CONFIRMATION_WORDS or normalized.startswith("confirm")

    def _is_cancel_message(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in _CANCEL_WORDS or normalized.startswith("cancel")

    def _extract_pending_action(
        self, query_context: dict[str, Any]
    ) -> dict[str, Any] | None:
        pending_action = query_context.get("pending_action")
        if isinstance(pending_action, dict):
            normalized, error = normalize_pending_action(pending_action)
            if error is None:
                return normalized
        return None

    def _clarification_response(
        self,
        message: str,
        query_context: dict[str, Any],
        task: AssistantTask | None = None,
        task_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reply = message
        payload = {
            "reply": reply,
            "message": reply,
            "tool": "none",
            "data": {"detail": message, "requires_clarification": True},
            "task": task.name if task is not None else "clarification",
            "task_context": task_context or {},
            "query_context": clear_pending_action(query_context),
        }
        return payload

    def _plan_from_pending_action(
        self, pending_action: dict[str, Any]
    ) -> AssistantPlan:
        tool = str(pending_action.get("tool") or "none")
        arguments = pending_action.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if tool == "update_deposit_correction":
            arguments = normalize_deposit_correction_arguments(arguments)
        intent_name = str(pending_action.get("intent_name") or "confirmation")
        intent_summary = str(
            pending_action.get("intent_summary") or "Pending confirmation"
        )
        return AssistantPlan(
            tool=tool,
            arguments=arguments,
            intent_name=intent_name,
            intent_summary=intent_summary,
        )

    def _execute_update_deposit_correction(self, arguments: Any) -> dict[str, Any]:
        return execute_deposit_correction(arguments)
