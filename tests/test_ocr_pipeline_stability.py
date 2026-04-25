from django.test import SimpleTestCase

from apps.extraction.services.ocr_service import score_ocr_text


class OcrPipelineStabilityTests(SimpleTestCase):
    def test_score_ocr_text_detects_bank_fields(self):
        self.assertEqual(score_ocr_text(""), 0)
        self.assertLess(
            score_ocr_text("abc"),
            score_ocr_text(
                "10/04/2026 08:30 ref 12345 consignacion banco valor $10.000"
            ),
        )
        self.assertGreater(
            score_ocr_text(
                "10/04/2026 08:30 ref 12345 consignacion banco valor $10.000"
            ),
            10,
        )
