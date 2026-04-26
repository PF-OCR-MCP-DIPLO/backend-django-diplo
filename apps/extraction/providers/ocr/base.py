"""Contrato base para proveedores OCR.

Cada implementación concreta debe exponer extracción de texto desde una imagen
o archivo compatible, respetando timeout y modelo cuando aplique.
"""


class BaseOCRProvider:
    """Define la interfaz mínima que consume el servicio de OCR."""

    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        raise NotImplementedError
