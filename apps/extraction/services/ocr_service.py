from apps.extraction.providers.ocr.ollama_vision import OllamaVisionOCRProvider
from apps.extraction.providers.ocr.tesseract import (
    TesseractOCRProvider,
    resolve_tesseract_language,
)


def _get_provider(provider_name):
    if provider_name == "ollama":
        return OllamaVisionOCRProvider(), "vision"
    if provider_name == "openai":
        raise ValueError("OCR provider openai is not implemented")
    if provider_name == "gemini":
        raise ValueError("OCR provider gemini is not implemented")
    if provider_name == "deepseek":
        raise ValueError("OCR provider deepseek is not implemented")
    raise ValueError(f"Unsupported OCR provider: {provider_name}")


def _run_tesseract(source_image, runtime_config):
    provider = TesseractOCRProvider()
    tess_lang = resolve_tesseract_language(runtime_config.ocr_model)
    source_image.image_file.open("rb")
    try:
        text = provider.extract_text(
            source_image.image_file,
            model_name=runtime_config.ocr_model,
        )
    finally:
        source_image.image_file.close()
    return {
        "text": text,
        "provider": "tesseract",
        "model": tess_lang,
        "mode": runtime_config.ocr_mode,
        "payload": {},
    }


def _run_vision(source_image, runtime_config):
    provider, resolved_mode = _get_provider(runtime_config.ocr_provider)
    source_image.image_file.open("rb")
    try:
        text = provider.extract_text(
            source_image.image_file,
            model_name=runtime_config.ocr_model,
            timeout_seconds=runtime_config.request_timeout_seconds,
        )
    finally:
        source_image.image_file.close()
    return {
        "text": text,
        "provider": runtime_config.ocr_provider,
        "model": runtime_config.ocr_model,
        "mode": resolved_mode,
        "payload": {},
    }


def extract_raw_text(source_image, runtime_config):
    if runtime_config.ocr_mode == "tesseract":
        return _run_tesseract(source_image, runtime_config)
    if runtime_config.ocr_mode == "vision":
        return _run_vision(source_image, runtime_config)
    if runtime_config.ocr_mode == "auto":
        if runtime_config.ocr_provider == "ollama":
            return _run_vision(source_image, runtime_config)
        return _run_tesseract(source_image, runtime_config)
    raise ValueError(f"Unsupported OCR mode: {runtime_config.ocr_mode}")
