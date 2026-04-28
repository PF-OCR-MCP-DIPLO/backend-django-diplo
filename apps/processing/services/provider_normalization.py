"""Helpers para normalizar nombres legacy de proveedores."""

from __future__ import annotations

OCR_PROVIDER_ALIASES = {
    "ollama_vision": "ollama",
}


def normalize_ocr_provider(provider_name: str | None) -> str:
    """Convierte aliases legacy de OCR al nombre canónico esperado."""
    normalized = (provider_name or "").strip()
    if not normalized:
        return "ollama"
    return OCR_PROVIDER_ALIASES.get(normalized, normalized)
