from django.test import SimpleTestCase

from apps.api.services.pending_actions import (
    build_pending_action,
    clear_pending_action,
    confirmation_message,
    normalize_pending_action,
    pending_action_requires_clarification,
    validate_pending_action,
)


class PendingActionContractTests(SimpleTestCase):
    def test_build_pending_action_uses_stable_public_shape(self):
        payload = build_pending_action(
            tool="update_deposit_correction",
            arguments={
                "job_id": 12,
                "deposit_id": 99,
                "referencia": "ABC123",
                "valor": 1000,
            },
            intent_name="deposit_correction",
            intent_summary="Actualizar referencia",
            job_id=12,
        )

        self.assertEqual(payload["tool"], "update_deposit_correction")
        self.assertEqual(payload["label"], "Corregir consignación")
        self.assertEqual(payload["risk"], "requires_confirmation")
        self.assertIn("id", payload)

    def test_normalize_pending_action_backfills_shape(self):
        normalized, error = normalize_pending_action(
            {
                "tool": "update_deposit_correction",
                "arguments": {"job_id": 12, "deposit_id": 99, "referencia": "ABC123"},
            }
        )

        self.assertIsNone(error)
        self.assertEqual(normalized["label"], "Corregir consignación")
        self.assertEqual(normalized["risk"], "requires_confirmation")
        self.assertIn("id", normalized)

    def test_pending_action_requires_clarification_for_missing_data(self):
        message = pending_action_requires_clarification(
            "update_deposit_correction",
            {"job_id": 12},
            job_id=12,
        )
        self.assertIsNotNone(message)
        self.assertIn("deposit_id", message)

        ok = pending_action_requires_clarification(
            "update_deposit_correction",
            {
                "job_id": 12,
                "deposit_id": 99,
                "referencia": "ABC123",
                "valor": 1000,
            },
            job_id=12,
        )
        self.assertIsNone(ok)

    def test_validate_pending_action_rejects_incomplete_or_invalid(self):
        self.assertEqual(
            validate_pending_action({"tool": "bad", "arguments": {}}, job_id=1),
            "La acción pendiente ya no es válida.",
        )
        self.assertEqual(
            validate_pending_action(
                {
                    "tool": "update_deposit_correction",
                    "arguments": {"job_id": 12, "deposit_id": 99},
                },
                job_id=12,
            ),
            "La acción pendiente está incompleta.",
        )

    def test_clear_pending_action_removes_only_pending_key(self):
        cleaned = clear_pending_action({"pending_action": {"tool": "x"}, "scope": "a"})
        self.assertNotIn("pending_action", cleaned)
        self.assertEqual(cleaned["scope"], "a")

    def test_confirmation_message_is_tool_specific(self):
        self.assertIn(
            "fila #99",
            confirmation_message(
                "update_deposit_correction",
                {"deposit_id": 99, "job_id": 12},
            ).lower(),
        )
