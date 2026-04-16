from django.conf import settings

from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider


def get_llm_provider():
    if settings.LLM_PROVIDER == "ollama_text":
        return OllamaTextLLMProvider()
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")


def extract_structured_data(source_image, raw_text):
    provider = get_llm_provider()
    return provider.extract(raw_text, source_image.source_name)
