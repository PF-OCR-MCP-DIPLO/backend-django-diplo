from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests
from django.conf import settings


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any): ...


class AssistantProviderError(RuntimeError):
    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int | None = None,
        detail: str | None = None,
        code: str = "provider_unavailable",
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.detail = detail or message
        self.code = code
        super().__init__(message)


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

    def _assistant_model_memory_message(self) -> str:
        return (
            "El modelo local configurado no cabe en la memoria disponible. "
            "Para equipos con poca RAM usa qwen3:1.7b. "
            "Si tienes más memoria disponible, llama3.2:3b puede ser una alternativa."
        )

    def _normalize_ollama_error(
        self,
        response: Any,
        detail: str | None,
    ) -> AssistantProviderError:
        normalized_detail = str(detail or "").strip()
        normalized_lower = normalized_detail.lower()
        if "requires more system memory" in normalized_lower:
            return AssistantProviderError(
                provider="ollama",
                status_code=getattr(response, "status_code", None),
                detail=normalized_detail or self._assistant_model_memory_message(),
                code="assistant_model_too_large",
                message=self._assistant_model_memory_message(),
            )
        return AssistantProviderError(
            provider="ollama",
            status_code=getattr(response, "status_code", None),
            detail=normalized_detail
            or "Ollama no pudo generar texto en este momento.",
            code="provider_unavailable",
            message=(
                f"Ollama devolvio {getattr(response, 'status_code', 'un error')} "
                f"al generar texto."
            ),
        )

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
        try:
            response = self.session.post(
                settings.OLLAMA_URL,
                json=payload,
                timeout=config.timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise AssistantProviderError(
                provider="ollama",
                status_code=None,
                detail="Ollama agotó el tiempo de espera.",
                code="provider_timeout",
                message="Ollama no respondio dentro del tiempo esperado.",
            ) from exc
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            detail = None
            if response is not None:
                try:
                    payload_data = response.json()
                    if isinstance(payload_data, dict):
                        detail = str(
                            payload_data.get("error")
                            or payload_data.get("message")
                            or payload_data.get("detail")
                            or payload_data
                        )
                except Exception:
                    detail = getattr(response, "text", "") or None
            raise self._normalize_ollama_error(response, detail) from exc
        except requests.RequestException as exc:
            raise AssistantProviderError(
                provider="ollama",
                status_code=None,
                detail=str(exc) or "No se pudo contactar a Ollama.",
                code="provider_unavailable",
                message="No se pudo contactar a Ollama.",
            ) from exc
        data = response.json()
        return str(data.get("response", ""))

    def _anthropic_generate(self, prompt: str, config: TextGenerationConfig) -> str:
        payload = {
            "model": config.model,
            "max_tokens": 1024,
            "temperature": config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = self.session.post(
                getattr(
                    settings, "ANTHROPIC_URL", "https://api.anthropic.com/v1/messages"
                ),
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
        except requests.Timeout as exc:
            raise AssistantProviderError(
                provider="anthropic",
                status_code=None,
                detail="Anthropic agotó el tiempo de espera.",
                code="provider_timeout",
                message="Anthropic no respondio dentro del tiempo esperado.",
            ) from exc
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            detail = getattr(response, "text", "") or "Anthropic devolvio un error."
            raise AssistantProviderError(
                provider="anthropic",
                status_code=getattr(response, "status_code", None),
                detail=detail,
                code="provider_unavailable",
                message="Anthropic devolvio un error al generar texto.",
            ) from exc
        except requests.RequestException as exc:
            raise AssistantProviderError(
                provider="anthropic",
                status_code=None,
                detail=str(exc) or "No se pudo contactar al proveedor.",
                code="provider_unavailable",
                message="No se pudo contactar al proveedor configurado.",
            ) from exc
        data = response.json()
        content = data.get("content") or []
        if content and isinstance(content, list):
            first_item = content[0] or {}
            if isinstance(first_item, dict):
                return str(first_item.get("text", ""))
        return str(data.get("text", ""))
