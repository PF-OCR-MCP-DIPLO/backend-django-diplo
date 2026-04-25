from django.test import SimpleTestCase

from apps.api.services.deposit_correction_tools import (
    deposit_correction_confirmation_message,
    deposit_correction_has_updates,
    deposit_correction_needs_clarification,
    deposit_correction_payload_for_correction,
    deposit_correction_success_description,
    deposit_correction_summary,
    extract_deposit_correction_deposit_id,
)


class DepositCorrectionToolsTests(SimpleTestCase):
    def test_extract_deposit_correction_deposit_id_uses_context_or_text(self):
        self.assertEqual(
            extract_deposit_correction_deposit_id("corrige la fila", {"depositId": 77}),
            77,
        )
        self.assertEqual(
            extract_deposit_correction_deposit_id("corrige la fila 44", {}),
            44,
        )

    def test_needs_clarification_detects_missing_fields(self):
        message = deposit_correction_needs_clarification({"job_id": 12}, job_id=12)
        self.assertIn("deposit_id", message)

        ok = deposit_correction_needs_clarification(
            {
                "job_id": 12,
                "deposit_id": 99,
                "referencia": "ABC123",
                "valor": 1000,
            },
            job_id=12,
        )
        self.assertIsNone(ok)

    def test_summary_and_confirmation_message_are_stable(self):
        summary = deposit_correction_summary(
            {"deposit_id": 99, "referencia": "ABC123", "valor": 1000}
        )
        self.assertIn("99", summary)
        self.assertIn("ABC123", summary)

        confirmation = deposit_correction_confirmation_message(
            {"deposit_id": 99, "referencia": "ABC123"}
        )
        self.assertIn("fila #99", confirmation.lower())

    def test_payload_normalization_and_success_description(self):
        payload = deposit_correction_payload_for_correction(
            {"job_id": 12, "deposit_id": 99, "referencia": "ABC123", "valor": 1000}
        )
        self.assertTrue(deposit_correction_has_updates(payload))
        self.assertEqual(payload["values"]["referencia"], "ABC123")

        description = deposit_correction_success_description(
            {"job_id": 12, "deposit_id": 99, "data": {"referencia": "ABC123"}}
        )
        self.assertIn("fila #99", description.lower())
