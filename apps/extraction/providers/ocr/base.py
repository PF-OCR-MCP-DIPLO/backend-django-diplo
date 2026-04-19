class BaseOCRProvider:
    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        raise NotImplementedError
