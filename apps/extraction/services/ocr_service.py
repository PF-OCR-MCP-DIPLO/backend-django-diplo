import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from apps.extraction.providers.ocr.ollama_vision import OllamaVisionOCRProvider
from apps.extraction.providers.ocr.stub import StubVisionOCRProvider
from apps.extraction.providers.ocr.tesseract import (
    TesseractOCRProvider,
    preprocess_image_for_ocr,
    resolve_tesseract_language,
)


@dataclass(frozen=True)
class OcrAttempt:
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
    selected_text: str
    selected_engine: str
    selected_provider: str
    selected_model: str | None
    selected_score: int
    attempts: list[OcrAttempt]
    fallback_used: bool


def _get_provider(provider_name):
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
    }


def _attempt_payload(attempt: OcrAttempt) -> dict[str, Any]:
    return {
        "engine": attempt.engine,
        "provider": attempt.provider,
        "model": attempt.model,
        "text": attempt.text,
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


def _run_tesseract(source_image, runtime_config):
    provider = TesseractOCRProvider()
    tess_lang = resolve_tesseract_language(runtime_config.ocr_model)
    processed_path = preprocess_image_for_ocr(
        source_image.image_file, binarize=True, sharpen=True
    )
    try:
        with open(processed_path, "rb") as processed_file:

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
        "mode": runtime_config.ocr_mode,
        "payload": _payload("tesseract", tess_lang, "tesseract", text),
    }


def _run_vision(source_image, runtime_config):
    provider, resolved_mode = _get_provider(runtime_config.ocr_provider)
    processed_path = preprocess_image_for_ocr(source_image.image_file, sharpen=True)
    try:
        with open(processed_path, "rb") as processed_file:
            text = provider.extract_text(
                processed_file,
                model_name=runtime_config.ocr_model,
                timeout_seconds=runtime_config.request_timeout_seconds,
            )
    finally:
        _remove_temp_path(processed_path)
    return {
        "text": text,
        "provider": runtime_config.ocr_provider,
        "model": runtime_config.ocr_model,
        "mode": resolved_mode,
        "payload": _payload(
            runtime_config.ocr_provider,
            runtime_config.ocr_model,
            resolved_mode,
            text,
        ),
    }


def _best_result(*results):
    return max(results, key=lambda item: score_ocr_text(item.get("text", "")))


def _attempt_result(
    *,
    engine: str,
    provider: str,
    model: str | None,
    runner,
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


def extract_raw_text(source_image, runtime_config):
    attempts: list[OcrAttempt] = []
    primary_runner = (
        _run_tesseract if runtime_config.ocr_mode == "tesseract" else _run_vision
    )
    fallback_runner = (
        _run_vision if primary_runner is _run_tesseract else _run_tesseract
    )
    primary_result, primary_attempt = _attempt_result(
        engine=runtime_config.ocr_mode,
        provider=(
            "tesseract"
            if primary_runner is _run_tesseract
            else runtime_config.ocr_provider
        ),
        model=(
            resolve_tesseract_language(runtime_config.ocr_model)
            if primary_runner is _run_tesseract
            else runtime_config.ocr_model
        ),
        runner=lambda: primary_runner(source_image, runtime_config),
    )
    attempts.append(primary_attempt)
    selected = primary_result
    fallback_used = False
    # Only the explicit auto mode should chain providers. When the user pins
    # vision or tesseract we keep that choice stable instead of silently
    # cascading into another engine after a low score.
    if runtime_config.ocr_mode == "auto":
        fallback_result, fallback_attempt = _attempt_result(
            engine="vision" if fallback_runner is _run_vision else "tesseract",
            provider=(
                runtime_config.ocr_provider
                if fallback_runner is _run_vision
                else "tesseract"
            ),
            model=(
                runtime_config.ocr_model
                if fallback_runner is _run_vision
                else resolve_tesseract_language(runtime_config.ocr_model)
            ),
            runner=lambda: fallback_runner(source_image, runtime_config),
        )
        attempts.append(fallback_attempt)
        if fallback_result is not None:
            fallback_used = True
            if selected is None or score_ocr_text(
                fallback_result.get("text", "")
            ) > score_ocr_text(selected.get("text", "")):
                selected = fallback_result
    if selected is None:
        raise RuntimeError("All OCR attempts failed")
    selected_payload = dict(selected)
    selected_payload["payload"] = {
        **selected_payload.get("payload", {}),
        "attempts": [_attempt_payload(item) for item in attempts],
        "selected_engine": selected_payload.get("mode", runtime_config.ocr_mode),
        "selected_provider": selected_payload.get("provider", ""),
        "selected_model": selected_payload.get("model"),
        "selected_score": score_ocr_text(selected_payload.get("text", "")),
        "fallback_used": fallback_used,
        "errors": [item.error for item in attempts if item.error],
    }
    return selected_payload
