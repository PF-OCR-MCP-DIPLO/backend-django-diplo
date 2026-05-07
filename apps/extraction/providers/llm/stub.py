"""Proveedor LLM determinista para pruebas y demos locales."""

from apps.extraction.providers.llm.base import BaseLLMProvider


class StubTextLLMProvider(BaseLLMProvider):
    """Devuelve una consignación fija sin depender de un modelo externo."""

    def extract(
        self,
        text,
        archivo_origen,
        model_name=None,
        timeout_seconds=None,
        max_retries=3,
        extraction_criteria=None,
        source_context=None,
    ):
        # Deterministic stub: always returns one valid record per image.
        # This enables stable E2E scenarios without requiring Ollama/OpenAI/etc.
        return [
            {
                "fecha_consignacion": "15/04/2026",
                "hora_consignacion": "09:30",
                "referencia": "REF001",
                "valor": 50000.0,
                "remitente": "DAVID GUEVARA",
                "archivo_origen": archivo_origen,
            }
        ]
