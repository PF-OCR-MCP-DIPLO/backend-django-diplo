"""Servicio de OCR con selección de proveedor, scoring y fallback.

Intenta recuperar texto útil desde una imagen procesada y conserva métricas de
cada intento para diagnóstico y comparación entre motores.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from django.conf import settings

from apps.extraction.providers.ocr.ollama_vision import OllamaVisionOCRProvider
from apps.extraction.providers.ocr.stub import StubVisionOCRProvider
from apps.extraction.providers.ocr.tesseract import (
    TesseractOCRProvider,
    preprocess_image_for_ocr,
    resolve_tesseract_language,
)
from apps.processing.services.provider_normalization import normalize_ocr_provider


@dataclass(frozen=True)
class OcrAttempt:
    """Registra un intento OCR individual con su score y metadatos."""

    engine: str
    provider: str
    model: str | None
    text: str
    score: int
    error: str | None
    duration_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OcrResult:
    """Resume el resultado seleccionado tras evaluar todos los intentos OCR."""

    selected_text: str
    selected_engine: str
    selected_provider: str
    selected_model: str | None
    selected_score: int
    attempts: list[OcrAttempt]
    fallback_used: bool


def _get_provider(provider_name):
    """Resuelve el proveedor OCR concreto según la configuración activa."""
    provider_name = normalize_ocr_provider(provider_name)
    if provider_name == "ollama":
        if getattr(settings, "STUB_PROVIDERS", False):
            return StubVisionOCRProvider(), "vision"
        return OllamaVisionOCRProvider(), "vision"
    if provider_name == "openai":
        raise ValueError("OCR provider openai is not implemented")
    if provider_name == "gemini":
        raise ValueError("OCR provider gemini is not implemented")
    if provider_name == "deepseek":
        raise ValueError("OCR provider deepseek is not implemented")
    raise ValueError(f"Unsupported OCR provider: {provider_name}")


def score_ocr_text(text):
    """Calcula una heurística simple de utilidad del texto OCR."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return 0

    import re

    score = min(len(normalized) // 20, 10)
    for keyword in (
        "consign",
        "comprobante",
        "banco",
        "referencia",
        "monto",
        "valor",
        "fecha",
        "hora",
        "transaccion",
        "transacción",
        "aprobada",
    ):
        if keyword in normalized:
            score += 3

    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", normalized):
        score += 4
    if re.search(r"\b\d{1,2}:\d{2}\b", normalized):
        score += 3
    if re.search(r"\$?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?\b", normalized):
        score += 4
    if len(normalized) < 25:
        score -= 4
    return max(score, 0)


def _payload(provider, model, mode, text):
    return {
        "effective_ocr_engine": mode,
        "effective_ocr_provider": provider,
        "effective_ocr_model": model,
        "score": score_ocr_text(text),
        "ocr_raw_text_chars": len(text or ""),
        "ocr_raw_text_sample": (text or "")[:500],
    }


def _attempt_payload(attempt: OcrAttempt) -> dict[str, Any]:
    return {
        "engine": attempt.engine,
        "provider": attempt.provider,
        "model": attempt.model,
        "text": attempt.text or "",
        "text_chars": len(attempt.text or ""),
        "text_sample": (attempt.text or "")[:500],
        "score": attempt.score,
        "error": attempt.error,
        "duration_ms": attempt.duration_ms,
        "metadata": attempt.metadata,
    }


def _remove_temp_path(path):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def _safe_timeout(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _tesseract_timeout_seconds(runtime_config) -> int:
    configured = _safe_timeout(
        getattr(settings, "TESSERACT_TIMEOUT_SECONDS", 90),
        90,
    )
    requested = _safe_timeout(runtime_config.request_timeout_seconds, configured)
    return max(5, min(requested, configured))


def _vision_timeout_seconds(runtime_config) -> int:
    requested = _safe_timeout(
        runtime_config.request_timeout_seconds,
        _safe_timeout(getattr(settings, "OLLAMA_TIMEOUT", 120), 120),
    )

    if runtime_config.ocr_mode == "auto":
        configured = _safe_timeout(
            getattr(settings, "OLLAMA_AUTO_VISION_TIMEOUT_SECONDS", 45),
            45,
        )
    else:
        configured = _safe_timeout(
            getattr(settings, "OLLAMA_VISION_TIMEOUT_SECONDS", 120),
            120,
        )

    return max(5, min(requested, configured))


def _run_tesseract(source_image, runtime_config):
    """Ejecuta Tesseract sobre una versión preprocesada de la imagen."""
    provider = TesseractOCRProvider()
    provider.timeout_seconds = _tesseract_timeout_seconds(runtime_config)

    tess_lang = resolve_tesseract_language(runtime_config.ocr_model)
    processed_path = preprocess_image_for_ocr(
        source_image.image_file,
    )

    try:

        class _TempImage:
            path = processed_path

            def seek(self, *_args, **_kwargs):
                return None

        text = provider.extract_text(
            _TempImage(),
            model_name=runtime_config.ocr_model,
        )
    finally:
        _remove_temp_path(processed_path)

    return {
        "text": text,
        "provider": "tesseract",
        "model": tess_lang,
        "mode": "tesseract",
        "payload": _payload("tesseract", tess_lang, "tesseract", text),
    }


def _run_vision(source_image, runtime_config):
    """Ejecuta OCR mediante un proveedor visión remoto o emulado."""
    provider_name = normalize_ocr_provider(runtime_config.ocr_provider)
    provider, resolved_mode = _get_provider(provider_name)
    processed_path = preprocess_image_for_ocr(
        source_image.image_file,
        binarize=False,
        sharpen=True,
    )

    try:
        with open(processed_path, "rb") as processed_file:
            text = provider.extract_text(
                processed_file,
                model_name=runtime_config.ocr_model,
                timeout_seconds=_vision_timeout_seconds(runtime_config),
            )
    finally:
        _remove_temp_path(processed_path)

    payload = _payload(
        provider_name,
        runtime_config.ocr_model,
        resolved_mode,
        text,
    )
    provider_error = getattr(provider, "last_error", None)
    if provider_error is not None:
        payload["provider_error_class"] = provider_error.__class__.__name__
        payload["provider_error_message"] = str(provider_error)[:500]

    return {
        "text": text,
        "provider": provider_name,
        "model": runtime_config.ocr_model,
        "mode": resolved_mode,
        "payload": payload,
    }


def _best_result(*results):
    candidates = [item for item in results if item is not None]
    if not candidates:
        return None

    def ranking(item):
        payload = item.get("payload") or {}
        valid_records = int(payload.get("valid_records_count") or 0)
        structured_records = int(payload.get("structured_records_count") or 0)
        return (
            valid_records,
            structured_records,
            score_ocr_text(item.get("text", "")),
            len(item.get("text", "") or ""),
        )

    return max(candidates, key=ranking)


def _attempt_result(
    *,
    engine: str,
    provider: str,
    model: str | None,
    runner: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any] | None, OcrAttempt]:
    started = time.monotonic()
    try:
        result = runner()
        text = result.get("text", "")
        score = score_ocr_text(text)
        attempt = OcrAttempt(
            engine=engine,
            provider=provider,
            model=model,
            text=text,
            score=score,
            error=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata=result.get("payload", {}),
        )
        return result, attempt
    except Exception as error:
        attempt = OcrAttempt(
            engine=engine,
            provider=provider,
            model=model,
            text="",
            score=0,
            error=str(error),
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={},
        )
        return None, attempt


def _result_with_attempts(
    selected: dict[str, Any] | None,
    attempts: list[OcrAttempt],
    fallback_used: bool,
) -> dict[str, Any]:
    if selected is None:
        errors = [attempt.error for attempt in attempts if attempt.error]
        detail = "; ".join(errors) if errors else "OCR did not return usable text"
        raise RuntimeError(detail)

    selected_text = selected.get("text", "")
    payload = dict(selected.get("payload") or {})
    payload.update(
        {
            "score": score_ocr_text(selected_text),
            "fallback_used": fallback_used,
            "attempts": [_attempt_payload(attempt) for attempt in attempts],
            "_attempt_texts": [
                {
                    "engine": attempt.engine,
                    "provider": attempt.provider,
                    "model": attempt.model,
                    "text": attempt.text,
                    "score": attempt.score,
                    "error": attempt.error,
                }
                for attempt in attempts
            ],
        }
    )

    return {
        "text": selected_text,
        "provider": selected.get("provider", ""),
        "model": selected.get("model"),
        "mode": selected.get("mode", ""),
        "payload": payload,
    }


def extract_raw_text(source_image, runtime_config):
    """Obtiene texto OCR bruto aplicando fallback entre motores disponibles.

    El resultado conserva todos los intentos para auditoría, pero selecciona la
    versión con mejor score para alimentar la etapa de estructuración.
    """
    attempts: list[OcrAttempt] = []
    fallback_used = False

    use_stub = bool(getattr(settings, "STUB_PROVIDERS", False))
    accept_score = _safe_timeout(getattr(settings, "AUTO_OCR_ACCEPT_SCORE", 8), 8)

    # Auto starts with Tesseract so a local OCR result is available quickly, then
    # compares the vision attempt before downstream structuring chooses a winner.
    if runtime_config.ocr_mode == "tesseract" and not use_stub:
        result, attempt = _attempt_result(
            engine="tesseract",
            provider="tesseract",
            model=resolve_tesseract_language(runtime_config.ocr_model),
            runner=lambda: _run_tesseract(source_image, runtime_config),
        )
        attempts.append(attempt)
        return _result_with_attempts(result, attempts, fallback_used=False)

    if runtime_config.ocr_mode == "vision" or use_stub:
        result, attempt = _attempt_result(
            engine="vision",
            provider=normalize_ocr_provider(runtime_config.ocr_provider),
            model=runtime_config.ocr_model,
            runner=lambda: _run_vision(source_image, runtime_config),
        )
        attempts.append(attempt)
        return _result_with_attempts(result, attempts, fallback_used=False)

    if runtime_config.ocr_mode == "auto":
        tesseract_result, tesseract_attempt = _attempt_result(
            engine="tesseract",
            provider="tesseract",
            model=resolve_tesseract_language(runtime_config.ocr_model),
            runner=lambda: _run_tesseract(source_image, runtime_config),
        )
        attempts.append(tesseract_attempt)

        selected = tesseract_result

        vision_result, vision_attempt = _attempt_result(
            engine="vision",
            provider=normalize_ocr_provider(runtime_config.ocr_provider),
            model=runtime_config.ocr_model,
            runner=lambda: _run_vision(source_image, runtime_config),
        )
        attempts.append(vision_attempt)
        fallback_used = vision_result is not None and (
            tesseract_result is None
            or tesseract_attempt.score < accept_score
            or score_ocr_text(vision_result.get("text", ""))
            > score_ocr_text(tesseract_result.get("text", ""))
        )
        selected = _best_result(tesseract_result, vision_result)

        return _result_with_attempts(selected, attempts, fallback_used=fallback_used)

    raise ValueError(f"Unsupported OCR mode: {runtime_config.ocr_mode}")
