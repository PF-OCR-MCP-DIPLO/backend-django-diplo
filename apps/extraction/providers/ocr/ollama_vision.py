"""Proveedor OCR visión basado en Ollama."""

import base64
import re

import requests
from django.conf import settings

from apps.extraction.providers.ocr.base import BaseOCRProvider

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def clean_ollama_text_response(value: str) -> str:
    """Normaliza respuestas de Ollama antes de usarlas como texto OCR."""
    text = str(value or "").strip()
    if not text:
        return ""

    text = _THINK_RE.sub("", text).strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:text|json|markdown)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

    return text


class OllamaVisionOCRProvider(BaseOCRProvider):
    """Ejecuta OCR visión sobre imágenes usando Ollama y conserva errores."""

    def __init__(self) -> None:
        self.last_error = None
        self.last_response_text = ""

    def build_prompt(self):
        """Construye el prompt OCR conservador usado para transcribir imágenes."""
        return (
            "Eres un motor OCR para comprobantes, consignaciones y transferencias bancarias.\n"
            "Tarea: transcribe TODO el texto visible de la imagen.\n"
            "No expliques tu razonamiento. No uses etiquetas <think>. No inventes datos.\n"
            "No corrijas montos, fechas, referencias, nombres, teléfonos ni números de comprobante.\n"
            "No resumas. No omitas encabezados, pie de página, nombres de comercio, punto de venta, enviado a, origen, destino, banco, cuenta ni teléfonos.\n"
            "No devuelvas JSON. Devuelve texto plano únicamente.\n"
            "Conserva saltos de línea en orden visual de arriba hacia abajo.\n"
            "Si un dato no es legible, escribe [ilegible].\n"
            "Incluye especialmente estos campos si aparecen:\n"
            "- fecha\n"
            "- hora\n"
            "- referencia\n"
            "- valor o monto\n"
            "- banco\n"
            "- comprobante\n"
            "- punto de venta\n"
            "- enviado a\n"
            "- enviado por\n"
            "- remitente\n"
            "- titular\n"
            "- comercio\n"
            "- empresa\n"
            "- cuenta origen o destino\n"
            "- teléfono o número Nequi\n"
            "Si ves textos enmascarados como GRO*** DYD***, COM*** SAS*** o similares, cópialos exactamente.\n"
            "Salida: texto plano transcrito, sin JSON y sin comentarios."
        )

    def extract_text(self, image_file, model_name=None, timeout_seconds=None):
        """Envía la imagen a Ollama y devuelve texto limpio para el pipeline."""
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
