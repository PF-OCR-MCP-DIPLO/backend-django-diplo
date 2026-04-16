from django.conf import settings

from apps.extraction.providers.ocr.ollama_vision import OllamaVisionOCRProvider


def get_ocr_provider():
    if settings.OCR_PROVIDER == "ollama_vision":
        return OllamaVisionOCRProvider()
    raise ValueError(f"Unsupported OCR provider: {settings.OCR_PROVIDER}")


def extract_raw_text(source_image):
    provider = get_ocr_provider()
    source_image.image_file.open("rb")
    try:
        return provider.extract_text(source_image.image_file)
    finally:
        source_image.image_file.close()
