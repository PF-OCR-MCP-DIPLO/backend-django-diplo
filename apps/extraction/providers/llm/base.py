"""Contrato base para proveedores LLM de estructuración."""


class BaseLLMProvider:
    """Define la interfaz consumida por el servicio de estructuración."""

    def extract(
        self, text, archivo_origen, model_name=None, timeout_seconds=None, max_retries=3
    ):
        raise NotImplementedError
