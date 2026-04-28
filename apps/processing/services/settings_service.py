"""Acceso, normalización y snapshot de configuración de procesamiento."""

from dataclasses import dataclass

from django.conf import settings

from apps.processing.models import ProcessingSettings
from apps.processing.services.extraction_criteria import (
    default_extraction_criteria,
    normalize_extraction_criteria,
)
from apps.processing.services.ollama_models import (
    get_available_models,
    list_installed_models,
)

OCR_PROVIDERS = [
    ProcessingSettings.Provider.OLLAMA,
    ProcessingSettings.Provider.OPENAI,
    ProcessingSettings.Provider.GEMINI,
    ProcessingSettings.Provider.DEEPSEEK,
]
LOW_RAM_ASSISTANT_MODEL = "qwen2.5:7b"
STANDARD_ASSISTANT_MODEL = "llama3.1:8b"
LLM_PROVIDERS = [
    ProcessingSettings.Provider.OLLAMA,
    ProcessingSettings.Provider.OPENAI,
    ProcessingSettings.Provider.GEMINI,
    ProcessingSettings.Provider.DEEPSEEK,
    ProcessingSettings.Provider.ANTHROPIC,
]


@dataclass(frozen=True)
class RuntimeProcessingConfig:
    """Snapshot inmutable de configuración efectiva para un ciclo de procesamiento."""

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
    """Obtiene o crea el singleton de configuración con valores por defecto."""
    defaults = {
        "ocr_mode": ProcessingSettings.OCRMode.VISION,
        "ocr_provider": ProcessingSettings.Provider.OLLAMA,
        "ocr_model": getattr(settings, "OLLAMA_VISION_MODEL", "gemma4:e2b"),
        "llm_provider": ProcessingSettings.Provider.OLLAMA,
        "llm_model": getattr(settings, "LLM_MODEL", settings.OLLAMA_MODEL),
        "assistant_provider": ProcessingSettings.Provider.OLLAMA,
        "assistant_model": getattr(
            settings, "ASSISTANT_MODEL", LOW_RAM_ASSISTANT_MODEL
        ),
        "assistant_show_debug_details": False,
        "request_timeout_seconds": settings.OLLAMA_TIMEOUT,
        "extraction_criteria": default_extraction_criteria(),
    }
    instance, _ = ProcessingSettings.objects.get_or_create(
        singleton_key="default", defaults=defaults
    )
    return instance


def get_runtime_config():
    """Construye una vista inmutable de la configuración activa."""
    config = get_or_create_processing_settings()

    resolved_ocr_mode = getattr(settings, "OCR_MODE", config.ocr_mode) or config.ocr_mode
    resolved_ocr_provider = (
        getattr(settings, "OCR_PROVIDER", config.ocr_provider) or config.ocr_provider
    )

    # Preferimos el modelo vision si el modo es vision/auto y el valor guardado
    # todavía apunta al lenguaje de Tesseract.
    resolved_ocr_model = (getattr(settings, "OCR_MODEL", config.ocr_model) or "").strip()
    if resolved_ocr_mode in (
        ProcessingSettings.OCRMode.VISION,
        ProcessingSettings.OCRMode.AUTO,
    ):
        if (
            not resolved_ocr_model
            or ":" not in resolved_ocr_model
            or resolved_ocr_model.lower() == "spa"
        ):
            resolved_ocr_model = getattr(settings, "OLLAMA_VISION_MODEL", "gemma4:e2b")
    elif resolved_ocr_mode == ProcessingSettings.OCRMode.TESSERACT:
        if not resolved_ocr_model:
            resolved_ocr_model = getattr(settings, "OCR_MODEL", "spa")

    return RuntimeProcessingConfig(
        ocr_mode=resolved_ocr_mode,
        ocr_provider=resolved_ocr_provider,
        ocr_model=resolved_ocr_model,
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
    """Serializa la configuración runtime en un snapshot apto para auditoría."""
    return {
        "ocr_mode": runtime_config.ocr_mode,
        "ocr_provider": runtime_config.ocr_provider,
        "effective_ocr_engine": runtime_config.ocr_mode,
        "effective_ocr_provider": runtime_config.ocr_provider,
        "effective_ocr_model": runtime_config.ocr_model,
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
    """Expone catálogos y requisitos de proveedores para el frontend."""
    try:
        ollama_models = list_installed_models()
    except Exception:
        ollama_models = []
    fallback_llm_models = [
        LOW_RAM_ASSISTANT_MODEL,
        STANDARD_ASSISTANT_MODEL,
        settings.OLLAMA_MODEL,
        "qwen2.5:3b",
    ]
    fallback_ocr_models = [settings.OLLAMA_VISION_MODEL, "gemma4:e2b", "moondream"]
    provider_models = {
        "ollama": {
            "ocr": ollama_models or fallback_ocr_models,
            "llm": ollama_models or fallback_llm_models,
        },
        "openai": {"ocr": [], "llm": []},
        "gemini": {"ocr": [], "llm": []},
        "deepseek": {"ocr": [], "llm": []},
        "anthropic": {"ocr": [], "llm": []},
    }
    provider_requirements = {
        provider: {
            "operational": provider == ProcessingSettings.Provider.OLLAMA,
            "requires_api_key": provider != ProcessingSettings.Provider.OLLAMA,
        }
        for provider in LLM_PROVIDERS
    }
    return {
        "ocr_modes": [choice[0] for choice in ProcessingSettings.OCRMode.choices],
        "providers": {
            "ocr": [provider.value for provider in OCR_PROVIDERS],
            "llm": [provider.value for provider in LLM_PROVIDERS],
        },
        "provider_models": provider_models,
        "provider_requirements": provider_requirements,
        "assistant_model_recommendations": {
            "low_ram": LOW_RAM_ASSISTANT_MODEL,
            "balanced": STANDARD_ASSISTANT_MODEL,
            "helper_text": (
                "Para equipos con ~5–6 GiB libres, usa qwen2.5:7b. "
                "Si tienes más memoria disponible, llama3.1:8b puede ser mejor para agente/tool use."
            ),
        },
    }


def get_ollama_models_snapshot():
    """Devuelve el snapshot crudo de modelos disponibles en Ollama."""
    return get_available_models()
