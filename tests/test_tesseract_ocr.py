import io
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from apps.extraction.providers.ocr.tesseract import (
    preprocess_image_for_ocr,
    resolve_tesseract_language,
)
from apps.extraction.services.ocr_service import _run_tesseract


class ResolveTesseractLanguageTests(SimpleTestCase):
    def test_vision_model_tag_falls_back_to_spa(self):
        self.assertEqual(resolve_tesseract_language("gemma4:e2b"), "spa")

    def test_blank_falls_back_to_spa(self):
        self.assertEqual(resolve_tesseract_language(""), "spa")
        self.assertEqual(resolve_tesseract_language("   "), "spa")
        self.assertEqual(resolve_tesseract_language(None), "spa")

    def test_tesseract_language_preserved(self):
        self.assertEqual(resolve_tesseract_language("spa"), "spa")
        self.assertEqual(resolve_tesseract_language("eng"), "eng")
        self.assertEqual(resolve_tesseract_language("spa+eng"), "spa+eng")

    def test_preprocess_image_returns_temp_path(self):
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc4\x15\x1b"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        path = preprocess_image_for_ocr(ContentFile(png, name="tiny.png"))
        self.assertTrue(path.exists())
        path.unlink(missing_ok=True)

    def test_tesseract_runner_preserves_midtone_receipt_text(self):
        """Regression test for DOCX receipt screenshots with low-contrast text."""
        image = Image.new("L", (80, 40), 255)
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 74, 24), fill=190)
        draw.point((0, 0), fill=0)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        source_image = SimpleNamespace(
            image_file=ContentFile(buffer.getvalue(), name="receipt.png")
        )
        runtime_config = SimpleNamespace(
            ocr_model="spa",
            request_timeout_seconds=30,
        )

        def fake_extract(provider, image_file, model_name="spa"):
            with Image.open(image_file.path) as processed:
                pixels = list(processed.convert("L").getdata())
            has_midtone_text = any(120 < pixel < 230 for pixel in pixels)
            if has_midtone_text:
                return "Fecha 03/03/2026 Referencia M06182308 Valor $20.000,00"
            return "EMPTY OCR RESULT"

        with patch(
            "apps.extraction.providers.ocr.tesseract.TesseractOCRProvider.extract_text",
            new=fake_extract,
        ):
            result = _run_tesseract(source_image, runtime_config)

        self.assertIn("Referencia M06182308", result["text"])
