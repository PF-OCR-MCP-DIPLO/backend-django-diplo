from django.conf import settings

from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider


def get_llm_provider(provider_name):
    if provider_name == "ollama":
        return OllamaTextLLMProvider()
    if provider_name == "openai":
        raise ValueError("LLM provider openai is not implemented")
    if provider_name == "gemini":
        raise ValueError("LLM provider gemini is not implemented")
    if provider_name == "deepseek":
        raise ValueError("LLM provider deepseek is not implemented")
    raise ValueError(f"Unsupported LLM provider: {provider_name}")


def extract_structured_data(source_image, raw_text, runtime_config):
    provider = get_llm_provider(runtime_config.llm_provider)
    records = provider.extract(
        raw_text,
        source_image.source_name,
        model_name=runtime_config.llm_model,
        timeout_seconds=runtime_config.request_timeout_seconds,
        max_retries=settings.LLM_MAX_RETRIES,
    )
    return {
        "records": records,
        "provider": runtime_config.llm_provider,
        "model": runtime_config.llm_model,
        "payload": {},
    }
