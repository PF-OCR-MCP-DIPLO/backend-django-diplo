from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.api.services.assistant_multiagent import AssistantPlan, ToolExecutionAgent
from apps.processing.models import ExtractedDeposit, ProcessRun, SourceImage


class AssistantCrudToolTests(TestCase):
    def setUp(self):
        self.executor = ToolExecutionAgent()
        self.process_run = ProcessRun.objects.create(
            source_docx=ContentFile(b"docx", name="test.docx"),
            original_filename="test.docx",
        )
        self.source_image = SourceImage.objects.create(
            process_run=self.process_run,
            sequence_index=1,
            image_file=ContentFile(b"img", name="image.png"),
            source_name="image.png",
        )

    def _execute(self, arguments: dict):
        plan = AssistantPlan(
            tool="crud_database",
            arguments=arguments,
            intent_name="test",
            intent_summary="crud test",
        )
        return self.executor.execute(plan, job_id=None)

    def test_create_update_delete_deposit(self):
        created = self._execute(
            {
                "operation": "create",
                "source": "deposits",
                "values": {
                    "process_run_id": self.process_run.id,
                    "source_image_id": self.source_image.id,
                    "sequence_index": 1,
                    "referencia": "REFCRUD001",
                    "valor": 150000,
                    "fecha_consignacion": "2026-04-22",
                    "hora_consignacion": "10:30",
                },
            }
        )
        self.assertEqual(created.get("operation"), "create")
        created_id = created.get("created_id")
        self.assertIsNotNone(created_id)

        updated = self._execute(
            {
                "operation": "update",
                "source": "deposits",
                "filters": [{"field": "id", "op": "eq", "value": created_id}],
                "values": {"valor": 200000},
            }
        )
        self.assertEqual(updated.get("operation"), "update")
        self.assertEqual(updated.get("updated_count"), 1)
        self.assertEqual(
            ExtractedDeposit.objects.get(pk=created_id).valor,
            Decimal("200000.00"),
        )

        deleted = self._execute(
            {
                "operation": "delete",
                "source": "deposits",
                "filters": [{"field": "id", "op": "eq", "value": created_id}],
            }
        )
        self.assertEqual(deleted.get("operation"), "delete")
        self.assertGreaterEqual(deleted.get("deleted_count", 0), 1)
        self.assertFalse(ExtractedDeposit.objects.filter(pk=created_id).exists())

    def test_read_operation_with_filters(self):
        ExtractedDeposit.objects.create(
            process_run=self.process_run,
            source_image=self.source_image,
            sequence_index=1,
            referencia="REFCRUD002",
            valor=Decimal("50000.00"),
            fecha_consignacion="2026-04-22",
            hora_consignacion="08:00",
        )
        payload = self._execute(
            {
                "operation": "read",
                "source": "deposits",
                "filters": [
                    {"field": "referencia", "op": "icontains", "value": "CRUD"}
                ],
                "limit": 10,
            }
        )
        self.assertEqual(payload.get("source"), "deposits")
        self.assertGreaterEqual(payload.get("meta", {}).get("rows_count", 0), 1)
