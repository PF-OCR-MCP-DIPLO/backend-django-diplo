from unittest.mock import patch

import requests
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from apps.extraction.providers.llm.ollama_text import OllamaTextLLMProvider
from apps.extraction.providers.ocr.ollama_vision import OllamaVisionOCRProvider


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class OllamaTextProviderTests(SimpleTestCase):
    def test_extract_returns_empty_for_blank_ocr(self):
        provider = OllamaTextLLMProvider()

        self.assertEqual(provider.extract("", "image.png"), [])
        self.assertEqual(provider.extract("EMPTY OCR RESULT", "image.png"), [])

    @override_settings(OLLAMA_URL="http://ollama.local", OLLAMA_TIMEOUT=3)
    def test_extract_retries_invalid_json_then_returns_records(self):
        valid_payload = {
            "response": (
                '{"consignaciones": ['
                '{"fecha_consignacion": "22/04/2026", '
                '"hora_consignacion": "08:30", '
                '"referencia": "REF123", "valor": 1000}'
                "]}"
            )
        }
        with patch(
            "apps.extraction.providers.llm.ollama_text.requests.post",
            side_effect=[
                FakeResponse({"response": "no json"}),
                FakeResponse(valid_payload),
            ],
        ) as mocked_post:
            result = OllamaTextLLMProvider().extract(
                "texto OCR",
                "image.png",
                model_name="gemma",
                timeout_seconds=9,
                max_retries=2,
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["referencia"], "REF123")
        self.assertEqual(result[0]["archivo_origen"], "image.png")
        self.assertEqual(mocked_post.call_args.kwargs["timeout"], 9)
        self.assertEqual(mocked_post.call_args.kwargs["json"]["model"], "gemma")

    def test_extract_handles_provider_request_errors(self):
        with (
            patch(
                "apps.extraction.providers.llm.ollama_text.requests.post",
                side_effect=requests.exceptions.RequestException,
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.time.sleep"
            ) as mocked_sleep,
        ):
            result = OllamaTextLLMProvider().extract(
                "texto OCR",
                "image.png",
                max_retries=2,
            )

        self.assertEqual(result, [])
        self.assertEqual(mocked_sleep.call_count, 2)


class OllamaVisionProviderTests(SimpleTestCase):
    def test_prompt_is_bank_consignation_specific(self):
        prompt = OllamaVisionOCRProvider().build_prompt()
        self.assertIn("consignaciones bancarias", prompt)
        self.assertIn("fecha, hora, referencia, valor", prompt)
        self.assertIn("JSON simple", prompt)

    @override_settings(OLLAMA_URL="http://ollama.local", OLLAMA_TIMEOUT=11)
    def test_extract_text_sends_base64_image_payload(self):
        with patch(
            "apps.extraction.providers.ocr.ollama_vision.requests.post",
            return_value=FakeResponse({"response": "texto"}),
        ) as mocked_post:
            result = OllamaVisionOCRProvider().extract_text(
                ContentFile(b"image-bytes", name="image.png"),
                model_name="vision-model",
                timeout_seconds=5,
            )

        self.assertEqual(result, "texto")
        payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "vision-model")
        self.assertEqual(payload["images"], ["aW1hZ2UtYnl0ZXM="])
        self.assertEqual(mocked_post.call_args.kwargs["timeout"], 5)
