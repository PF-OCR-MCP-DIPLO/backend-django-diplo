from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import requests
from django.conf import settings


@dataclass(frozen=True)
class OllamaModelInfo:
    name: str
    label: str
    size: int | None = None
    modified_at: str | None = None


def _tags_url_from_ollama_url(ollama_url: str) -> str:
    parsed = urlparse(ollama_url)
    path = parsed.path or ""
    if path.endswith("/api/generate"):
        path = path[: -len("/api/generate")] + "/api/tags"
    elif path.endswith("/generate"):
        path = path[: -len("/generate")] + "/api/tags"
    elif path.endswith("/api/tags"):
        path = path
    else:
        base_path = path.rsplit("/", 1)[0] if "/" in path else ""
        path = f"{base_path}/api/tags"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _extract_model_names(payload: object) -> list[str]:
    models: list[str] = []
    if not isinstance(payload, dict):
        return models
    for item in payload.get("models", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            models.append(name)
    return models


def _extract_models(payload: object) -> list[OllamaModelInfo]:
    models: list[OllamaModelInfo] = []
    if not isinstance(payload, dict):
        return models
    for item in payload.get("models", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        models.append(
            OllamaModelInfo(
                name=name,
                label=str(item.get("name_display") or name).strip() or name,
                size=item.get("size") if isinstance(item.get("size"), int) else None,
                modified_at=str(item.get("modified_at") or item.get("modifiedAt") or "").strip() or None,
            )
        )
    return models


def list_installed_models(timeout: int | float = 5.0) -> list[str]:
    url = _tags_url_from_ollama_url(getattr(settings, "OLLAMA_URL", ""))
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return _extract_model_names(response.json())
    except Exception:
        return []


def get_available_models(timeout: int | float = 5.0) -> dict[str, object]:
    url = _tags_url_from_ollama_url(getattr(settings, "OLLAMA_URL", ""))
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        models = _extract_models(response.json())
        return {
            "provider": "ollama",
            "available": True,
            "models": [
                {
                    "name": model.name,
                    "label": model.label,
                    "size": model.size,
                    "modifiedAt": model.modified_at,
                }
                for model in models
            ],
            "error": None,
        }
    except Exception as exc:
        return {
            "provider": "ollama",
            "available": False,
            "models": [],
            "error": str(exc) or "Unable to list Ollama models.",
        }
