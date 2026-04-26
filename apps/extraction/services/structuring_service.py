import requests
from django.conf import settings

from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider
from apps.extraction.providers.llm.stub import StubTextLLMProvider
from apps.processing.services.diagnostics import stable_hash, truncate_debug_text


def get_llm_provider(provider_name):
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


def extract_structured_data(source_image, raw_text, runtime_config):
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

    provider_error = getattr(provider, "last_error", None)
    if isinstance(provider_error, requests.exceptions.Timeout):
        raise TimeoutError(
            f"LLM provider timed out after {timeout_seconds} seconds"
        ) from provider_error

    raw_response = getattr(provider, "last_response_text", "") or ""
    clean_response = getattr(provider, "last_clean_response_text", "") or ""

    return {
        "records": records,
        "provider": runtime_config.llm_provider,
        "model": runtime_config.llm_model,
        "payload": {
            "raw_text_chars": len(raw_text or ""),
            "raw_text_sha256": stable_hash(raw_text or ""),
            "raw_text_sample": truncate_debug_text(raw_text or ""),
            "max_ocr_chars_for_llm": max_ocr_chars,
            "ocr_text_truncated_for_llm": was_truncated,
            "prompt_chars": prompt_chars,
            "response_chars": len(raw_response),
            "clean_response_chars": len(clean_response),
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
