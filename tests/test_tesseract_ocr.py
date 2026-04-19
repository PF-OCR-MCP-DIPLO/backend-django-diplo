from django.test import SimpleTestCase

from apps.extraction.providers.ocr.tesseract import resolve_tesseract_language


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
