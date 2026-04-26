"""Servicio HTTP del chat del asistente.

Normaliza el contexto de consulta y protege el contrato entre la vista REST,
el agente conversacional y el frontend.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from apps.api.services.assistant_agent import AssistantAgent

logger = logging.getLogger(__name__)


def normalize_query_context(raw_query_context: Any) -> dict[str, Any]:
    """Convierte el contexto de consulta recibido desde la API en un dict seguro."""
    if not isinstance(raw_query_context, dict):
        return {}
    return dict(raw_query_context)


class AssistantChatService:
    """Orquesta la respuesta del asistente para el caso de uso HTTP."""

    def __init__(
        self,
        agent_factory: Callable[[], AssistantAgent] | None = None,
    ) -> None:
        self.agent_factory = agent_factory or AssistantAgent

    def answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta el agente y degrada a una respuesta segura si falla."""
        query_context = normalize_query_context(payload.get("query_context"))
        try:
            agent = self.agent_factory()
            result = agent.answer(
                messages=payload["messages"],
                job_id=payload.get("job_id"),
                errors=payload.get("errors", 0),
                query_context=query_context,
            )
        except Exception as exc:  # pragma: no cover - defensive application guard
            logger.warning(
                "Assistant chat service fallback: %s: %s",
                exc.__class__.__name__,
                exc,
            )
            result = {
                "reply": (
                    "El asistente no esta disponible temporalmente. "
                    "Intenta de nuevo en unos momentos."
                ),
                "message": (
                    "El asistente no esta disponible temporalmente. "
                    "Intenta de nuevo en unos momentos."
                ),
                "tool": "none",
                "data": {"detail": "assistant_unavailable"},
                "debug": {
                    "intent": None,
                    "confidence": None,
                    "selected_tool": "none",
                    "fallback_used": True,
                    "errors": [f"{exc.__class__.__name__}: {exc}"],
                },
                "query_context": query_context,
            }
        return self._normalize_response(result, query_context)

    def _normalize_response(
        self, result: Any, query_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Uniforma la forma de respuesta esperada por la API y el frontend."""
        if not isinstance(result, dict):
            result = {"reply": str(result), "tool": "none", "data": {}}
        response = dict(result)
        response.setdefault("reply", "")
        response.setdefault("message", response.get("reply", ""))
        response.setdefault("tool", "none")
        response.setdefault("data", {})
        response.setdefault("query_context", query_context)
        response.setdefault("pending_action", None)
        response.setdefault("used_context", query_context)
        debug = response.get("debug")
        if not isinstance(debug, dict):
            debug = {}
        debug.setdefault("intent", response.get("task"))
        debug.setdefault("confidence", None)
        debug.setdefault("selected_tool", response.get("tool"))
        debug.setdefault("fallback_used", response.get("tool") == "none")
        debug.setdefault("errors", [])
        response["debug"] = debug
        response.setdefault("show_debug_details", False)
        return response

    def finalize_response(
        self,
        response: dict[str, Any],
        *,
        show_debug_details: bool,
    ) -> dict[str, Any]:
        """Ajusta la respuesta final según la visibilidad de debug configurada."""
        normalized = self._normalize_response(
            response, normalize_query_context(response.get("query_context"))
        )
        normalized["show_debug_details"] = bool(show_debug_details)

        data = normalized.get("data")
        if not isinstance(data, dict):
            data = {}
            normalized["data"] = data

        debug = normalized.get("debug")
        if not isinstance(debug, dict):
            debug = {
                "intent": normalized.get("task"),
                "confidence": None,
                "selected_tool": normalized.get("tool"),
                "fallback_used": normalized.get("tool") == "none",
                "errors": [],
            }
        if not show_debug_details:
            data.pop("error", None)
            debug["errors"] = []
        normalized["debug"] = debug
        normalized["message"] = normalized.get("message") or normalized.get("reply", "")
        return normalized
