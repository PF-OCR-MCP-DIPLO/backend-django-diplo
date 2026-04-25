from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import requests
from django.conf import settings


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


def list_installed_models(timeout: int | float = 5.0) -> list[str]:
    url = _tags_url_from_ollama_url(getattr(settings, "OLLAMA_URL", ""))
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return _extract_model_names(response.json())
    except Exception:
        return []
