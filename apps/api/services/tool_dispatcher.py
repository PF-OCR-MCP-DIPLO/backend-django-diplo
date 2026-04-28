"""Despachador central de herramientas del asistente.

Convierte una intención de alto nivel en ejecución real sobre el backend.
"""

from __future__ import annotations

from typing import Any

from apps.api.services.assistant_multiagent import AssistantPlan, ToolExecutionAgent


class ToolDispatcher:
    """Encapsula la ejecución de herramientas sobre el agente de planificación."""

    def __init__(self, executor: ToolExecutionAgent | None = None) -> None:
        self._executor = executor or ToolExecutionAgent()

    def execute(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        job_id: int | None = None,
        intent_name: str = "dispatcher",
        intent_summary: str = "Tool dispatch execution",
    ) -> Any:
        """Ejecuta una herramienta bajo el flujo estándar del asistente.

        Args:
            tool: Nombre lógico de la herramienta.
            arguments: Parámetros serializables para la herramienta.
            job_id: Contexto opcional de corrida para herramientas de dominio.
            intent_name: Etiqueta técnica de la intención en trazas.
            intent_summary: Resumen humano para depuración.

        Returns:
            Respuesta cruda entregada por el ejecutor de herramientas.
        """
        plan = AssistantPlan(
            tool=tool,
            arguments=arguments or {},
            intent_name=intent_name,
            intent_summary=intent_summary,
        )
        return self._executor.execute(plan, job_id=job_id)


_DEFAULT_DISPATCHER = ToolDispatcher()


def execute_tool(
    tool: str,
    arguments: dict[str, Any] | None = None,
    job_id: int | None = None,
) -> Any:
    """Atajo funcional para ejecutar herramientas sin instanciar dispatcher.

    Se usa en capas de integración (por ejemplo MCP) para reutilizar las mismas
    reglas de ejecución que la API del asistente.
    """
    return _DEFAULT_DISPATCHER.execute(
        tool=tool,
        arguments=arguments,
        job_id=job_id,
    )
