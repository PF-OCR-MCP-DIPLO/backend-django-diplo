from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests
from django.conf import settings


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any): ...


@dataclass(frozen=True)
class TextGenerationConfig:
    provider: str
    model: str
    timeout: int
    api_key: str = ""
    temperature: float = 0.2
    num_predict: int = 256


class AssistantTextClient:
    """Small adapter for external text providers used by assistant agents."""

    def __init__(self, session: HttpSession | None = None) -> None:
        self.session = session or requests

    def generate(self, prompt: str, config: TextGenerationConfig) -> str:
        if config.provider == "anthropic":
            return self._anthropic_generate(prompt, config)
        return self._ollama_generate(prompt, config)

    def _ollama_generate(self, prompt: str, config: TextGenerationConfig) -> str:
        payload = {
            "model": config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.num_predict,
            },
        }
        response = self.session.post(
            settings.OLLAMA_URL,
            json=payload,
            timeout=config.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", ""))

    def _anthropic_generate(self, prompt: str, config: TextGenerationConfig) -> str:
        payload = {
            "model": config.model,
            "max_tokens": 1024,
            "temperature": config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self.session.post(
            getattr(settings, "ANTHROPIC_URL", "https://api.anthropic.com/v1/messages"),
            json=payload,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": getattr(
                    settings, "ANTHROPIC_VERSION", "2023-06-01"
                ),
                "content-type": "application/json",
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content") or []
        if content and isinstance(content, list):
            first_item = content[0] or {}
            if isinstance(first_item, dict):
                return str(first_item.get("text", ""))
        return str(data.get("text", ""))
