import base64

import requests
from django.conf import settings

from apps.extraction.providers.ocr.base import BaseOCRProvider


class OllamaVisionOCRProvider(BaseOCRProvider):
    def extract_text(self, image_file):
        image_file.seek(0)
        image_b64 = base64.b64encode(image_file.read()).decode("utf-8")
        payload = {
            "model": settings.OLLAMA_VISION_MODEL,
            "prompt": "Transcribe all text in this image. Return only the raw text, no conversational filler.",
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0,
            },
        }
        response = requests.post(
            settings.OLLAMA_URL,
            json=payload,
            timeout=settings.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "")
