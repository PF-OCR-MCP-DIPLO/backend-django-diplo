from apps.extraction.providers.llm.base import BaseLLMProvider


class StubTextLLMProvider(BaseLLMProvider):
    def extract(
        self, text, archivo_origen, model_name=None, timeout_seconds=None, max_retries=3
    ):
        # Deterministic stub: always returns one valid record per image.
        # This enables stable E2E scenarios without requiring Ollama/OpenAI/etc.
        return [
            {
                "fecha_consignacion": "15/04/2026",
                "hora_consignacion": "09:30",
                "referencia": "REF001",
                "valor": 50000.0,
                "archivo_origen": archivo_origen,
            }
        ]

