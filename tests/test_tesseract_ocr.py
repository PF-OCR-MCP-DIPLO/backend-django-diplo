from django.test import SimpleTestCase

from apps.extraction.providers.ocr.tesseract import (
    preprocess_image_for_ocr,
    resolve_tesseract_language,
)


class ResolveTesseractLanguageTests(SimpleTestCase):
    def test_vision_model_tag_falls_back_to_spa(self):
        self.assertEqual(resolve_tesseract_language("gemma4:e2b"), "spa")

    def test_blank_falls_back_to_spa(self):
        self.assertEqual(resolve_tesseract_language(""), "spa")
        self.assertEqual(resolve_tesseract_language("   "), "spa")
        self.assertEqual(resolve_tesseract_language(None), "spa")

    def test_tesseract_language_preserved(self):
        self.assertEqual(resolve_tesseract_language("eng"), "eng")
        self.assertEqual(resolve_tesseract_language("eng+spa"), "eng+spa")

    def test_preprocess_image_returns_temp_path(self):
        from django.core.files.base import ContentFile

        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc4\x15\x1b"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        path = preprocess_image_for_ocr(ContentFile(png, name="tiny.png"))
        self.assertTrue(path.exists())
        path.unlink(missing_ok=True)
