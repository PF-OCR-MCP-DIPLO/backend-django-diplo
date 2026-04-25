import base64

import requests
from django.conf import settings

from apps.extraction.providers.ocr.base import BaseOCRProvider


class OllamaVisionOCRProvider(BaseOCRProvider):
    def build_prompt(self):
        return (
            "Eres un OCR especializado en consignaciones bancarias.\n"
            "Extrae fielmente solo el texto visible, sin inventar datos ni corregir montos.\n"
            "Prioriza fecha, hora, referencia, valor o monto, banco y número de comprobante.\n"
            "Devuelve una sola línea por consignación o por bloque visual.\n"
            "Si un dato no es legible, omítelo o marca [ilegible].\n"
            "Si el pipeline lo soporta, responde como JSON simple con una lista llamada consignaciones.\n"
            "Cada elemento debe contener fecha, hora, referencia, valor, banco y comprobante cuando existan."
        )

    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        image_file.seek(0)
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")
        payload = {
            "model": model_name or settings.OLLAMA_VISION_MODEL,
            "prompt": self.build_prompt(),
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0,
            },
        }
        response = requests.post(
            settings.OLLAMA_URL,
            json=payload,
            timeout=timeout_seconds or settings.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "")
