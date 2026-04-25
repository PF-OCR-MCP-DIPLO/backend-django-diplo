from __future__ import annotations

from typing import Any, Callable

from apps.api.services.assistant_agent import AssistantAgent


class AssistantChatService:
    """Application service for the assistant chat HTTP use case."""

    def __init__(
        self,
        agent_factory: Callable[[], AssistantAgent] | None = None,
    ) -> None:
        self.agent_factory = agent_factory or AssistantAgent

    def answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent = self.agent_factory()
        result = agent.answer(
            messages=payload["messages"],
            job_id=payload.get("job_id"),
            errors=payload.get("errors", 0),
        )
        if not isinstance(result, dict):
            result = {
                "reply": str(result),
                "tool": "none",
                "data": {},
            }

        response = dict(result)
        response.setdefault("reply", "")
        response.setdefault("tool", "none")
        response.setdefault("data", {})
        response.setdefault("query_context", payload.get("query_context", {}))
        response.setdefault("show_debug_details", False)
        return response
