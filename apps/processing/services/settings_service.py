from dataclasses import dataclass

from django.conf import settings

from apps.processing.models import ProcessingSettings


@dataclass(frozen=True)
class RuntimeProcessingConfig:
    ocr_mode: str
    ocr_provider: str
    ocr_model: str
    llm_provider: str
    llm_model: str
    ocr_api_key: str
    llm_api_key: str
    request_timeout_seconds: int


def get_or_create_processing_settings():
    defaults = {
        "ocr_mode": ProcessingSettings.OCRMode.VISION,
        "ocr_provider": ProcessingSettings.Provider.OLLAMA,
        "ocr_model": settings.OLLAMA_VISION_MODEL,
        "llm_provider": ProcessingSettings.Provider.OLLAMA,
        "llm_model": settings.OLLAMA_MODEL,
        "request_timeout_seconds": settings.OLLAMA_TIMEOUT,
    }
    instance, _ = ProcessingSettings.objects.get_or_create(
        singleton_key="default", defaults=defaults
    )
    return instance


def get_runtime_config():
    config = get_or_create_processing_settings()
    return RuntimeProcessingConfig(
        ocr_mode=config.ocr_mode,
        ocr_provider=config.ocr_provider,
        ocr_model=config.ocr_model,
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        ocr_api_key=config.ocr_api_key,
        llm_api_key=config.llm_api_key,
        request_timeout_seconds=config.request_timeout_seconds,
    )


def as_snapshot_dict(runtime_config):
    return {
        "ocr_mode": runtime_config.ocr_mode,
        "ocr_provider": runtime_config.ocr_provider,
        "ocr_model": runtime_config.ocr_model,
        "llm_provider": runtime_config.llm_provider,
        "llm_model": runtime_config.llm_model,
        "has_ocr_api_key": bool(runtime_config.ocr_api_key),
        "has_llm_api_key": bool(runtime_config.llm_api_key),
        "request_timeout_seconds": runtime_config.request_timeout_seconds,
    }


def available_options():
    return {
        "ocr_modes": [choice[0] for choice in ProcessingSettings.OCRMode.choices],
        "providers": {
            "ocr": [choice[0] for choice in ProcessingSettings.Provider.choices],
            "llm": [choice[0] for choice in ProcessingSettings.Provider.choices],
        },
        "provider_models": {
            "ollama": {
                "ocr": [settings.OLLAMA_VISION_MODEL, "llava:7b", "moondream"],
                "llm": [settings.OLLAMA_MODEL, "llama3.2:3b", "qwen2.5:3b"],
            },
            "openai": {"ocr": [], "llm": []},
            "gemini": {"ocr": [], "llm": []},
            "deepseek": {"ocr": [], "llm": []},
        },
        "provider_requirements": {
            "ollama": {
                "operational": True,
                "requires_api_key": False,
            },
            "openai": {
                "operational": False,
                "requires_api_key": True,
            },
            "gemini": {
                "operational": False,
                "requires_api_key": True,
            },
            "deepseek": {
                "operational": False,
                "requires_api_key": True,
            },
        },
    }
