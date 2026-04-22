from __future__ import annotations

from typing import Any

from apps.api.services.assistant_multiagent import AssistantPlan, ToolExecutionAgent


class ToolDispatcher:
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
    return _DEFAULT_DISPATCHER.execute(
        tool=tool,
        arguments=arguments,
        job_id=job_id,
    )
