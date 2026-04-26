"""Proveedor OCR determinista para pruebas y demos locales."""

from apps.extraction.providers.ocr.base import BaseOCRProvider


class StubVisionOCRProvider(BaseOCRProvider):
    """Devuelve un resultado fijo para escenarios sin dependencias externas."""

    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        # Deterministic stub for E2E/local demos without external OCR dependencies.
        return "STUB OCR RESULT: CONSIGNACION REF=REF001 VALOR=50000 FECHA=15/04/2026 HORA=09:30"
