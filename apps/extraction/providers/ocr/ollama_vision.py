import base64
import re

import requests
from django.conf import settings

from apps.extraction.providers.ocr.base import BaseOCRProvider

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def clean_ollama_text_response(value: str) -> str:
    """Normalize Ollama responses from thinking models before the OCR text is used."""
    text = str(value or "").strip()
    if not text:
        return ""

    text = _THINK_RE.sub("", text).strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:text|json|markdown)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

    return text


class OllamaVisionOCRProvider(BaseOCRProvider):
    def __init__(self) -> None:
        self.last_error = None
        self.last_response_text = ""

    def build_prompt(self):
        return (
            "Eres un motor OCR para comprobantes y consignaciones bancarias.\n"
            "Tarea: transcribe únicamente el texto visible de la imagen.\n"
            "No expliques tu razonamiento. No uses etiquetas <think>. No inventes datos.\n"
            "No corrijas montos, fechas, referencias ni números de comprobante.\n"
            "Prioriza fecha, hora, referencia, valor o monto, banco y número de comprobante.\n"
            "Devuelve una sola línea por consignación o por bloque visual.\n"
            "Si un dato no es legible, omítelo o marca [ilegible].\n"
            "Si el pipeline lo soporta, responde como JSON simple con una lista llamada consignaciones.\n"
            "Cada elemento debe contener fecha, hora, referencia, valor, banco y comprobante cuando existan.\n"
            "Devuelve texto plano, compacto, una línea por bloque visual o consignación."
        )

    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        self.last_error = None
        self.last_response_text = ""

        image_file.seek(0)
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

        num_predict = int(getattr(settings, "OLLAMA_OCR_NUM_PREDICT", 256))
        timeout_value = int(timeout_seconds or settings.OLLAMA_TIMEOUT)

        payload = {
            "model": model_name or settings.OLLAMA_VISION_MODEL,
            "prompt": self.build_prompt(),
            "images": [image_b64],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
        }

        try:
            response = requests.post(
                settings.OLLAMA_URL,
                json=payload,
                timeout=timeout_value,
            )
            response.raise_for_status()
            raw_response = response.json().get("response", "")
            cleaned = clean_ollama_text_response(raw_response)
            self.last_response_text = cleaned
            return cleaned
        except requests.exceptions.RequestException as error:
            self.last_error = error
            raise
