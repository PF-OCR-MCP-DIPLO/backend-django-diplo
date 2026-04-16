class BaseOCRProvider:
    def extract_text(self, image_file):
        raise NotImplementedError
