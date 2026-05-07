"""Servicio de estructuración con LLM sobre texto OCR.

Convierte texto bruto en consignaciones normalizadas usando el proveedor LLM
activo y conserva metadatos del prompt y la respuesta.
"""

import re

import requests
from django.conf import settings

from apps.common.utils.currency import smart_parse_currency
from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider
from apps.extraction.providers.llm.stub import StubTextLLMProvider
from apps.processing.services.diagnostics import stable_hash, truncate_debug_text

DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
MONEY_RE = re.compile(
    r"(?:COP|COL\$|\$)?\s*\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{2})?|\b\d{4,}(?:[.,]\d{2})?\b",
    re.IGNORECASE,
)
REFERENCE_LABEL_RE = re.compile(
    r"\b(?:ref(?:erencia)?|comprobante|transacci[oó]n|operaci[oó]n|n[uú]mero|no\.?)"
    r"[:#\s-]*([A-Z0-9][A-Z0-9\-/]{2,})\b",
    re.IGNORECASE,
)
REFERENCE_TOKEN_RE = re.compile(r"\b[A-Z0-9][A-Z0-9\-/]{4,}\b", re.IGNORECASE)


def get_llm_provider(provider_name):
    """Resuelve el proveedor LLM configurado o un stub de pruebas."""
    if provider_name == "ollama":
        if getattr(settings, "STUB_PROVIDERS", False):
            return StubTextLLMProvider()
        return OllamaTextLLMProvider()
    if provider_name == "openai":
        raise ValueError("LLM provider openai is not implemented")
    if provider_name == "gemini":
        raise ValueError("LLM provider gemini is not implemented")
    if provider_name == "deepseek":
        raise ValueError("LLM provider deepseek is not implemented")
    raise ValueError(f"Unsupported LLM provider: {provider_name}")


def _safe_int(value, fallback):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _llm_timeout_seconds(runtime_config):
    requested = _safe_int(
        runtime_config.request_timeout_seconds, settings.OLLAMA_TIMEOUT
    )
    configured = _safe_int(
        getattr(settings, "OLLAMA_LLM_TIMEOUT_SECONDS", settings.OLLAMA_TIMEOUT),
        settings.OLLAMA_TIMEOUT,
    )
    return max(5, min(requested, configured))


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    parts = re.split(r"[/-]", value)
    if len(parts) != 3:
        return None
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    return f"{int(day):02d}/{int(month):02d}/{int(year):04d}"


def _normalize_time(value: str | None) -> str | None:
    if not value:
        return None
    hour, minute = value.split(":", 1)
    return f"{int(hour):02d}:{int(minute):02d}"


def _looks_like_reference(token: str) -> bool:
    lowered = token.lower()
    if DATE_RE.fullmatch(token) or TIME_RE.fullmatch(token):
        return False
    if lowered in {"valor", "fecha", "hora", "banco", "consignacion", "consignación"}:
        return False
    return bool(re.search(r"[a-zA-Z]", token) or len(re.sub(r"\D", "", token)) >= 5)


def extract_heuristic_records(raw_text: str, archivo_origen: str = "") -> list[dict]:
    """Extrae candidatos basicos cuando el LLM no devuelve registros.

    Este fallback es deliberadamente conservador: solo crea un candidato cuando
    encuentra valor monetario y una referencia plausible en la misma linea o en
    el texto cercano.
    """
    text = raw_text or ""
    if not text.strip():
        return []

    records = []
    seen = set()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text.strip()]

    global_date = DATE_RE.search(text)
    global_time = TIME_RE.search(text)

    for index, line in enumerate(lines):
        money_matches = list(MONEY_RE.finditer(line))
        if not money_matches:
            continue

        context = " ".join(lines[max(0, index - 1) : min(len(lines), index + 2)])
        ref_match = REFERENCE_LABEL_RE.search(context)
        referencia = ref_match.group(1).strip() if ref_match else None
        if not referencia:
            for token_match in REFERENCE_TOKEN_RE.finditer(context):
                token = token_match.group(0).strip()
                if _looks_like_reference(token):
                    referencia = token
                    break
        if not referencia:
            continue

        for money_match in money_matches:
            valor = smart_parse_currency(money_match.group(0))
            if valor is None or valor <= 0:
                continue

            date_match = DATE_RE.search(context) or global_date
            time_match = TIME_RE.search(context) or global_time
            fecha = _normalize_date(date_match.group(0)) if date_match else None
            hora = _normalize_time(time_match.group(0)) if time_match else None
            signature = (referencia.upper(), float(valor))
            if signature in seen:
                continue
            seen.add(signature)
            records.append(
                {
                    "fecha_consignacion": fecha,
                    "hora_consignacion": hora,
                    "referencia": referencia,
                    "valor": float(valor),
                    "archivo_origen": archivo_origen,
                    "_extraction_source": "heuristic_fallback",
                    "_fallback_observation": (
                        "Registro extraido por fallback heuristico; requiere revision."
                    ),
                }
            )

    return records


def extract_structured_data(source_image, raw_text, runtime_config):
    """Pide al proveedor LLM que estructure el texto OCR en consignaciones.

    Side Effects:
        Ejecuta llamadas de red y puede lanzar `TimeoutError` o errores de
        proveedor si la respuesta no es utilizable.
    """
    provider = get_llm_provider(runtime_config.llm_provider)

    max_ocr_chars = int(getattr(settings, "MAX_OCR_CHARS_FOR_LLM", 12000))
    effective_raw_text = raw_text or ""
    was_truncated = len(effective_raw_text) > max_ocr_chars
    if was_truncated:
        effective_raw_text = effective_raw_text[:max_ocr_chars]

    prompt_chars = None
    if hasattr(provider, "_build_initial_prompt"):
        try:
            prompt_chars = len(
                provider._build_initial_prompt(  # noqa: SLF001
                    effective_raw_text,
                    runtime_config.extraction_criteria,
                )
            )
        except Exception:
            prompt_chars = None

    timeout_seconds = _llm_timeout_seconds(runtime_config)

    records = provider.extract(
        effective_raw_text,
        source_image.source_name,
        model_name=runtime_config.llm_model,
        timeout_seconds=timeout_seconds,
        max_retries=settings.LLM_MAX_RETRIES,
        extraction_criteria=runtime_config.extraction_criteria,
    )
    llm_records_count = len(records)

    provider_error = getattr(provider, "last_error", None)
    if isinstance(provider_error, requests.exceptions.Timeout):
        raise TimeoutError(
            f"LLM provider timed out after {timeout_seconds} seconds"
        ) from provider_error

    raw_response = getattr(provider, "last_response_text", "") or ""
    clean_response = getattr(provider, "last_clean_response_text", "") or ""
    fallback_records = []
    fallback_used = False
    if not records:
        fallback_records = extract_heuristic_records(
            effective_raw_text,
            getattr(source_image, "source_name", ""),
        )
        if fallback_records:
            records = fallback_records
            fallback_used = True

    return {
        "records": records,
        "provider": runtime_config.llm_provider,
        "model": runtime_config.llm_model,
        "payload": {
            "raw_text_chars": len(raw_text or ""),
            "raw_text_sha256": stable_hash(raw_text or ""),
            "raw_text_sample": truncate_debug_text(raw_text or ""),
            "ocr_raw_text_chars": len(raw_text or ""),
            "ocr_raw_text_sample": truncate_debug_text(raw_text or ""),
            "structured_records_count": len(records),
            "llm_structured_records_count": llm_records_count,
            "heuristic_fallback_used": fallback_used,
            "heuristic_records_count": len(fallback_records),
            "max_ocr_chars_for_llm": max_ocr_chars,
            "ocr_text_truncated_for_llm": was_truncated,
            "prompt_chars": prompt_chars,
            "response_chars": len(raw_response),
            "clean_response_chars": len(clean_response),
            "raw_response_preview": truncate_debug_text(raw_response),
            "clean_response_preview": truncate_debug_text(clean_response),
            "empty_provider_response": not raw_response.strip(),
            "llm_timeout_seconds": timeout_seconds,
            "provider_error_class": (
                provider_error.__class__.__name__ if provider_error else None
            ),
            "provider_error_message": (
                truncate_debug_text(str(provider_error), 500)
                if provider_error
                else None
            ),
        },
    }
