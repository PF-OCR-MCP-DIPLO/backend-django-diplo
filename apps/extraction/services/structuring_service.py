"""Servicio de estructuración con LLM sobre texto OCR.

Convierte texto bruto en consignaciones normalizadas usando el proveedor LLM
activo y conserva metadatos del prompt y la respuesta.
"""

import re
from datetime import date

import requests
from django.conf import settings

from apps.common.utils.currency import smart_parse_currency
from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider
from apps.extraction.providers.llm.stub import StubTextLLMProvider
from apps.processing.services.diagnostics import stable_hash, truncate_debug_text

DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
TEXTUAL_DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s*(?:de\s+)?(?P<month>"
    + "|".join(SPANISH_MONTHS)
    + r")\s*(?:de\s+)?(?P<year>20\d{2}|\d{2})\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(
    r"(?:COP|COL\$|\$)?\s*\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{2})?|\b\d{4,}(?:[.,]\d{2})?\b",
    re.IGNORECASE,
)
REFERENCE_LABEL_RE = re.compile(
    r"\b(?:ref(?:erencia)?|comprobante|transacci[oó]n|operaci[oó]n|no\.?)"
    r"[:#\s-]*([A-Z0-9][A-Z0-9\-/]{2,})\b",
    re.IGNORECASE,
)
REFERENCE_TOKEN_RE = re.compile(r"\b[A-Z0-9][A-Z0-9\-/]{4,}\b", re.IGNORECASE)
AMOUNT_LABEL_RE = re.compile(
    r"(?:¿?\s*cu[aá]nto\??|valor|monto|importe(?:\s+total)?|total\s+a\s+pagar)",
    re.IGNORECASE,
)
AMOUNT_BLOCKLIST_LABEL_RE = re.compile(
    r"(?:n[uú]mero\s+nequi|llave|cuenta(?:\s+a\s+debitar)?|identificaci[oó]n|"
    r"banco\s+destino|celular|tel[eé]fono|documento|c[eé]dula|nit)",
    re.IGNORECASE,
)
GENERIC_REFERENCES = {
    "nequi",
    "banco",
    "disponible",
    "pap",
    "valor",
    "monto",
    "referencia",
}


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


def _safe_date(day: int, month: int, year: int) -> str | None:
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return parsed.strftime("%d/%m/%Y")


def _normalize_year(value: str) -> int:
    year = int(value)
    return year + 2000 if year < 100 else year


def detect_explicit_date(text: str) -> str | None:
    """Detecta una fecha visible en OCR, incluyendo formato textual en español."""
    value = text or ""
    textual = TEXTUAL_DATE_RE.search(value)
    if textual:
        month = SPANISH_MONTHS.get(textual.group("month").lower())
        if month:
            normalized = _safe_date(
                int(textual.group("day")),
                month,
                _normalize_year(textual.group("year")),
            )
            if normalized:
                return normalized
    numeric = DATE_RE.search(value)
    return _normalize_date(numeric.group(0)) if numeric else None


def detect_explicit_time(text: str) -> str | None:
    match = TIME_RE.search(text or "")
    return _normalize_time(match.group(0)) if match else None


def _looks_like_reference(token: str) -> bool:
    lowered = token.lower()
    if DATE_RE.fullmatch(token) or TIME_RE.fullmatch(token):
        return False
    if lowered in {"valor", "fecha", "hora", "banco", "consignacion", "consignación"}:
        return False
    return bool(re.search(r"[a-zA-Z]", token) or len(re.sub(r"\D", "", token)) >= 5)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _compact_time_reason(digits: str) -> str:
    if len(digits) not in {3, 4}:
        return ""
    hour = int(digits[:-2])
    minute = int(digits[-2:])
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return "amount_looks_like_time"
    return ""


def _amount_rejection_reason(match, text: str, parsed_value) -> str:
    token = match.group(0)
    digits = _digits(token)
    numeric_value = int(float(parsed_value)) if parsed_value is not None else 0
    window_start = max(0, match.start() - 80)
    window_end = min(len(text), match.end() + 40)
    nearby = text[window_start:window_end]
    before = text[window_start : match.start()]
    immediate_before = text[max(0, match.start() - 30) : match.start()]
    has_immediate_amount_context = bool(
        AMOUNT_LABEL_RE.search(immediate_before) or "$" in token
    )

    if AMOUNT_BLOCKLIST_LABEL_RE.search(nearby) and not has_immediate_amount_context:
        return "amount_near_non_amount_label"
    if numeric_value in range(1900, 2101):
        return "amount_looks_like_year"
    if _compact_time_reason(digits):
        return "amount_looks_like_time"
    if len(digits) in {9, 10} and digits.startswith("3"):
        return "amount_looks_like_phone"
    if len(digits) >= 9 and not AMOUNT_LABEL_RE.search(before) and "$" not in token:
        return "amount_without_money_context"
    if not AMOUNT_LABEL_RE.search(before) and "$" not in nearby:
        return "amount_without_money_context"
    return ""


def _amount_score(match, text: str) -> tuple[int, int]:
    token = match.group(0)
    before = text[max(0, match.start() - 70) : match.start()]
    label_score = 4 if AMOUNT_LABEL_RE.search(before) else 0
    symbol_score = 2 if "$" in token or "$" in before[-10:] else 0
    return label_score + symbol_score, -match.start()


def _find_reference(text: str, diagnostics: list[dict] | None = None) -> str | None:
    explicit = []
    for match in REFERENCE_LABEL_RE.finditer(text or ""):
        label_window = text[max(0, match.start() - 25) : match.start()]
        token = match.group(1).strip(" .,:;")
        if AMOUNT_BLOCKLIST_LABEL_RE.search(label_window):
            continue
        if _looks_like_reference(token):
            explicit.append(token)
    if explicit:
        return explicit[0]

    for token_match in REFERENCE_TOKEN_RE.finditer(text or ""):
        token = token_match.group(0).strip(" .,:;")
        if _looks_like_reference(token):
            return token
    if diagnostics is not None:
        diagnostics.append(
            {"candidate_type": "reference", "reason": "missing_transaction_reference"}
        )
    return None


def _is_generic_reference(value: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in GENERIC_REFERENCES


def extract_heuristic_records(
    raw_text: str, archivo_origen: str = "", diagnostics: list[dict] | None = None
) -> list[dict]:
    """Extrae candidatos basicos cuando el LLM no devuelve registros.

    Este fallback es deliberadamente conservador: solo crea un candidato cuando
    encuentra valor monetario y una referencia plausible en la misma linea o en
    el texto cercano.
    """
    text = raw_text or ""
    if not text.strip():
        return []

    normalized_text = re.sub(r"[ \t]+", " ", text)
    amount_candidates = []
    for money_match in MONEY_RE.finditer(normalized_text):
        candidate_text = money_match.group(0)
        valor = smart_parse_currency(candidate_text)
        if valor is None or valor <= 0:
            reason = "amount_not_parseable"
        else:
            reason = _amount_rejection_reason(money_match, normalized_text, valor)
        candidate_payload = {
            "candidate_type": "amount",
            "text": candidate_text,
            "span": [money_match.start(), money_match.end()],
            "parsed_value": valor,
        }
        if reason:
            candidate_payload["reason"] = reason
            if diagnostics is not None:
                diagnostics.append(candidate_payload)
            continue
        candidate_payload["score"] = _amount_score(money_match, normalized_text)[0]
        amount_candidates.append((money_match, valor, candidate_payload))

    if not amount_candidates:
        if diagnostics is not None:
            diagnostics.append(
                {"candidate_type": "record", "reason": "missing_transaction_amount"}
            )
        return []

    referencia = _find_reference(normalized_text, diagnostics)
    if not referencia or _is_generic_reference(referencia):
        if diagnostics is not None:
            diagnostics.append(
                {
                    "candidate_type": "record",
                    "reason": (
                        "reference_too_generic"
                        if referencia
                        else "missing_transaction_reference"
                    ),
                    "referencia": referencia,
                }
            )
        return []

    selected_match, selected_value, selected_payload = max(
        amount_candidates, key=lambda item: _amount_score(item[0], normalized_text)
    )
    if diagnostics is not None:
        for _, _, payload in amount_candidates:
            emitted_payload = dict(payload)
            emitted_payload["reason"] = (
                "selected_transaction_amount"
                if payload is selected_payload
                else "lower_confidence_amount_candidate"
            )
            diagnostics.append(emitted_payload)

    return [
        {
            "fecha_consignacion": detect_explicit_date(normalized_text),
            "hora_consignacion": detect_explicit_time(normalized_text),
            "referencia": referencia,
            "valor": float(selected_value),
            "archivo_origen": archivo_origen,
            "_extraction_source": "heuristic_fallback",
            "_fallback_observation": (
                "Registro extraido por fallback heuristico conservador; requiere revision."
            ),
            "_fallback_selected_amount_text": selected_match.group(0),
        }
    ]


def _source_context_payload(source_image) -> dict:
    return {
        "context_date": getattr(source_image, "context_date", "") or "",
        "context_text": getattr(source_image, "context_text", "") or "",
        "context_payload": getattr(source_image, "context_payload", {}) or {},
    }


def _apply_date_context(records, source_image, raw_text) -> tuple[list[dict], dict]:
    explicit_date = detect_explicit_date(raw_text)
    explicit_time = detect_explicit_time(raw_text)
    context_date = getattr(source_image, "context_date", "") or ""
    enriched = []
    for record in records or []:
        if not isinstance(record, dict):
            enriched.append(record)
            continue
        item = dict(record)
        record_date = _normalize_date(item.get("fecha_consignacion"))
        date_source = "record"
        if explicit_date:
            item["fecha_consignacion"] = explicit_date
            date_source = "image_explicit"
        elif record_date:
            item["fecha_consignacion"] = record_date
        elif context_date:
            item["fecha_consignacion"] = context_date
            date_source = "docx_context"
        else:
            item["fecha_consignacion"] = None
            date_source = "missing"
        if not item.get("hora_consignacion") and explicit_time:
            item["hora_consignacion"] = explicit_time
        elif item.get("hora_consignacion"):
            item["hora_consignacion"] = _normalize_time(item.get("hora_consignacion"))
        item["_date_resolution"] = {
            "explicit_ocr_date": explicit_date,
            "context_date": context_date,
            "final_date": item.get("fecha_consignacion"),
            "date_source": date_source,
        }
        enriched.append(item)
    return enriched, {
        "explicit_ocr_date": explicit_date,
        "explicit_ocr_time": explicit_time,
        "context_date": context_date,
        "date_source": (
            "image_explicit"
            if explicit_date
            else ("docx_context" if context_date else "missing")
        ),
    }


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
    source_context = _source_context_payload(source_image)
    if hasattr(provider, "_build_initial_prompt"):
        try:
            prompt_chars = len(
                provider._build_initial_prompt(  # noqa: SLF001
                    effective_raw_text,
                    runtime_config.extraction_criteria,
                    source_context=source_context,
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
        source_context=source_context,
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
    fallback_diagnostics = []
    fallback_started = False
    if not records:
        fallback_started = True
        fallback_records = extract_heuristic_records(
            effective_raw_text,
            getattr(source_image, "source_name", ""),
            diagnostics=fallback_diagnostics,
        )
        if fallback_records:
            records = fallback_records
            fallback_used = True
    records, date_resolution = _apply_date_context(records, source_image, raw_text)

    llm_failure_event = None
    if not raw_response.strip():
        llm_failure_event = "llm_empty_response"
    elif provider_error:
        error_class = provider_error.__class__.__name__
        if error_class == "JSONDecodeError":
            llm_failure_event = "llm_invalid_json"
        elif error_class == "ValidationError":
            llm_failure_event = "llm_validation_failed"
        else:
            llm_failure_event = error_class
    elif not records and clean_response:
        llm_failure_event = "llm_validation_failed"

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
            "heuristic_fallback_started": fallback_started,
            "heuristic_records_count": len(fallback_records),
            "heuristic_candidates": fallback_diagnostics,
            "heuristic_rejected_count": len(
                [
                    item
                    for item in fallback_diagnostics
                    if item.get("reason") not in {"selected_transaction_amount"}
                ]
            ),
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
            "llm_failure_event": llm_failure_event,
            "context_date": source_context.get("context_date"),
            "context_text": truncate_debug_text(source_context.get("context_text")),
            "context_payload": source_context.get("context_payload"),
            "explicit_ocr_date": date_resolution.get("explicit_ocr_date"),
            "explicit_ocr_time": date_resolution.get("explicit_ocr_time"),
            "final_date_source": date_resolution.get("date_source"),
        },
    }
