from dataclasses import dataclass

from django.conf import settings

from apps.processing.models import ProcessingSettings
from apps.processing.services.extraction_criteria import (
    default_extraction_criteria,
    normalize_extraction_criteria,
)
from apps.processing.services.ollama_models import get_available_models, list_installed_models


@dataclass(frozen=True)
class RuntimeProcessingConfig:
    ocr_mode: str
    ocr_provider: str
    ocr_model: str
    llm_provider: str
    llm_model: str
    assistant_provider: str
    assistant_model: str
    assistant_api_key: str
    assistant_temperature: float
    assistant_num_predict: int
    assistant_show_debug_details: bool
    ocr_api_key: str
    llm_api_key: str
    request_timeout_seconds: int
    extraction_criteria: dict


def get_or_create_processing_settings():
    defaults = {
        "ocr_mode": ProcessingSettings.OCRMode.VISION,
        "ocr_provider": ProcessingSettings.Provider.OLLAMA,
        "ocr_model": settings.OLLAMA_VISION_MODEL,
        "llm_provider": ProcessingSettings.Provider.OLLAMA,
        "llm_model": settings.OLLAMA_MODEL,
        "assistant_provider": ProcessingSettings.Provider.OLLAMA,
        "assistant_model": settings.OLLAMA_MODEL,
        "assistant_show_debug_details": False,
        "request_timeout_seconds": settings.OLLAMA_TIMEOUT,
        "extraction_criteria": default_extraction_criteria(),
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
        assistant_provider=config.assistant_provider,
        assistant_model=config.assistant_model,
        assistant_api_key=config.assistant_api_key,
        assistant_temperature=config.assistant_temperature,
        assistant_num_predict=config.assistant_num_predict,
        assistant_show_debug_details=config.assistant_show_debug_details,
        ocr_api_key=config.ocr_api_key,
        llm_api_key=config.llm_api_key,
        request_timeout_seconds=config.request_timeout_seconds,
        extraction_criteria=normalize_extraction_criteria(config.extraction_criteria),
    )


def as_snapshot_dict(runtime_config):
    return {
        "ocr_mode": runtime_config.ocr_mode,
        "ocr_provider": runtime_config.ocr_provider,
        "ocr_model": runtime_config.ocr_model,
        "llm_provider": runtime_config.llm_provider,
        "llm_model": runtime_config.llm_model,
        "assistant_provider": runtime_config.assistant_provider,
        "assistant_model": runtime_config.assistant_model,
        "assistant_show_debug_details": runtime_config.assistant_show_debug_details,
        "has_ocr_api_key": bool(runtime_config.ocr_api_key),
        "has_llm_api_key": bool(runtime_config.llm_api_key),
        "has_assistant_api_key": bool(runtime_config.assistant_api_key),
        "assistant_temperature": runtime_config.assistant_temperature,
        "assistant_num_predict": runtime_config.assistant_num_predict,
        "request_timeout_seconds": runtime_config.request_timeout_seconds,
        "extraction_criteria": runtime_config.extraction_criteria,
    }


def available_options():
    ollama_models = list_installed_models()
    fallback_llm_models = [settings.OLLAMA_MODEL, "llama3.2:3b", "qwen2.5:3b"]
    fallback_ocr_models = [settings.OLLAMA_VISION_MODEL, "llava:7b", "moondream"]
    return {
        "ocr_modes": [choice[0] for choice in ProcessingSettings.OCRMode.choices],
        "providers": {
            "ocr": [choice[0] for choice in ProcessingSettings.Provider.choices],
            "llm": [choice[0] for choice in ProcessingSettings.Provider.choices],
        },
        "provider_models": {
            "ollama": {
                "ocr": ollama_models or fallback_ocr_models,
                "llm": ollama_models or fallback_llm_models,
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


def get_ollama_models_snapshot():
    return get_available_models()
