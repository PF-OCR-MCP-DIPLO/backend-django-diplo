class BaseLLMProvider:
    def extract(
        self, text, archivo_origen, model_name=None, timeout_seconds=None, max_retries=3
    ):
        raise NotImplementedError
