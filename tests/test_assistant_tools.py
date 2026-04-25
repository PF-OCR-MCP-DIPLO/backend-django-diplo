from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from apps.api.services.assistant_multiagent import AssistantPlan, ToolExecutionAgent
from apps.api.services.tool_risk import get_tool_risk_level, tool_requires_confirmation
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    SourceImage,
)


class AssistantToolExecutionTests(TestCase):
    def setUp(self):
        self.executor = ToolExecutionAgent()
        self.process_run = ProcessRun.objects.create(
            source_docx=ContentFile(b"docx", name="test.docx"),
            original_filename="test.docx",
            status=ProcessRun.Status.COMPLETED,
            total_records=2,
        )
        self.source_image = SourceImage.objects.create(
            process_run=self.process_run,
            sequence_index=1,
            image_file=ContentFile(b"img", name="image.png"),
            source_name="image.png",
        )
        self.deposit = ExtractedDeposit.objects.create(
            process_run=self.process_run,
            source_image=self.source_image,
            sequence_index=1,
            referencia="REFTOOL001",
            valor=Decimal("100000.00"),
            fecha_consignacion="2026-04-22",
            hora_consignacion="08:30",
        )
        ExtractionLog.objects.create(
            process_run=self.process_run,
            source_image=self.source_image,
            sequence_index=1,
            stage="ocr",
            raw_text="ok",
        )

    def _execute(
        self, tool: str, arguments: dict | None = None, job_id: int | None = None
    ):
        plan = AssistantPlan(
            tool=tool,
            arguments=arguments or {},
            intent_name="test",
            intent_summary="tool test",
        )
        return self.executor.execute(plan, job_id=job_id)

    def test_basic_tools_and_missing_job_id_are_controlled(self):
        self.assertEqual(self._execute("none"), {"kind": "none"})
        self.assertEqual(self._execute("health_check")["status"], "ok")
        self.assertEqual(
            self._execute("unsupported")["detail"], "Unsupported tool: unsupported"
        )
        self.assertEqual(
            self._execute("get_job_status")["detail"],
            "job_id is required",
        )
        self.assertEqual(
            self._execute("get_job_logs")["detail"],
            "job_id is required",
        )

    def test_update_deposit_correction_requires_job_and_deposit(self):
        missing = self._execute(
            "update_deposit_correction",
            {
                "job_id": self.process_run.id,
                "referencia": "REFNEW",
                "valor": 123,
            },
        )
        self.assertIn("invalid", missing.get("detail", "").lower())

        wrong_job = self._execute(
            "update_deposit_correction",
            {
                "job_id": self.process_run.id + 100,
                "deposit_id": self.deposit.id,
                "fecha_consignacion": "2026-04-22",
                "hora_consignacion": "09:00",
                "referencia": "REFNEW",
                "valor": 123,
            },
        )
        self.assertIn("job_id invalido", wrong_job["detail"])

        wrong_deposit = self._execute(
            "update_deposit_correction",
            {
                "job_id": self.process_run.id,
                "deposit_id": self.deposit.id + 100,
                "fecha_consignacion": "2026-04-22",
                "hora_consignacion": "09:00",
                "referencia": "REFNEW",
                "valor": 123,
            },
        )
        self.assertIn("deposit_id no pertenece", wrong_deposit["detail"])

    def test_tool_risk_levels_are_classified(self):
        self.assertEqual(get_tool_risk_level("query_database"), "read_only")
        self.assertEqual(
            get_tool_risk_level("update_processing_settings"), "requires_confirmation"
        )
        self.assertTrue(tool_requires_confirmation("update_processing_settings"))
        self.assertEqual(get_tool_risk_level("query_database_sql"), "restricted")

    def test_job_tools_return_serialized_payloads(self):
        status_payload = self._execute("get_job_status", job_id=self.process_run.id)
        self.assertEqual(status_payload["id"], self.process_run.id)
        self.assertEqual(
            status_payload["source_images"][0]["deposits"][0]["referencia"],
            "REFTOOL001",
        )

        logs_payload = self._execute("get_job_logs", job_id=self.process_run.id)
        self.assertEqual(len(logs_payload), 1)
        self.assertEqual(logs_payload[0]["stage"], "ocr")

        last_record = self._execute("get_last_record_value", job_id=self.process_run.id)
        self.assertEqual(last_record["last_record"]["referencia"], "REFTOOL001")

        summary = self._execute("get_completed_records_summary")
        self.assertEqual(summary["jobs_count"], 1)
        self.assertEqual(summary["total_records"], 1)
        self.assertEqual(summary["total_value"], "100000")

    def test_update_deposit_correction_updates_single_row(self):
        payload = self._execute(
            "update_deposit_correction",
            {
                "job_id": self.process_run.id,
                "deposit_id": self.deposit.id,
                "fecha_consignacion": "2026-04-23",
                "hora_consignacion": "10:00",
                "referencia": "REFFIX001",
                "valor": 250000,
            },
        )

        self.assertEqual(payload["operation"], "update")
        self.assertEqual(payload["job_id"], self.process_run.id)
        self.assertEqual(payload["deposit_id"], self.deposit.id)
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.referencia, "REFFIX001")

    def test_query_database_validates_source_and_applies_filters(self):
        invalid = self._execute("query_database", {"query": {"source": "nope"}})
        self.assertIn("source invalido", invalid["detail"])

        payload = self._execute(
            "query_database",
            {
                "query": {
                    "source": "deposits",
                    "select": ["referencia", "valor", "not_allowed"],
                    "filters": [
                        {"field": "referencia", "op": "icontains", "value": "TOOL"},
                        {"field": "valor", "op": "between", "value": [1, 200000]},
                        {"field": "created_at", "op": "date_eq", "value": "today"},
                    ],
                    "order_by": [{"field": "valor", "direction": "desc"}],
                    "limit": 5,
                }
            },
        )

        self.assertEqual(payload["source"], "deposits")
        self.assertEqual(payload["rows"][0]["referencia"], "REFTOOL001")
        self.assertEqual(payload["meta"]["rows_count"], 1)
        self.assertTrue(payload["meta"]["warnings"])

    def test_query_database_supports_grouping_and_aggregations(self):
        payload = self._execute(
            "query_database",
            {
                "query": {
                    "source": "deposits",
                    "group_by": ["fecha_consignacion"],
                    "aggregations": [
                        {"type": "sum", "field": "valor", "as": "total_valor"},
                        {"type": "count", "field": "id", "as": "total"},
                    ],
                    "order_by": [{"field": "fecha_consignacion", "direction": "desc"}],
                }
            },
        )

        self.assertEqual(payload["rows"][0]["fecha_consignacion"], "2026-04-22")
        self.assertEqual(payload["rows"][0]["total_valor"], "100000")
        self.assertEqual(payload["rows"][0]["total"], 1)
        self.assertTrue(payload["meta"]["has_aggregations"])

    def test_readonly_sql_validation_blocks_unsafe_statements(self):
        blocked = self._execute(
            "query_database_sql",
            {"sql": "DELETE FROM apps_processing_processrun", "limit": 10},
        )
        self.assertIn("Solo se permiten", blocked["detail"])

        multi = self._execute(
            "query_database_sql",
            {"sql": "SELECT 1; SELECT 2", "limit": 10},
        )
        self.assertIn("multiples sentencias", multi["detail"])

    def test_readonly_sql_executes_select(self):
        payload = self._execute(
            "query_database_sql",
            {
                "sql": "SELECT id, original_filename FROM processing_processrun",
                "limit": 1,
            },
        )

        self.assertEqual(payload["meta"]["rows_count"], 1)
        self.assertEqual(payload["rows"][0]["original_filename"], "test.docx")

    @override_settings(ALLOW_UNSAFE_SQL=True)
    def test_unsafe_sql_mode_reports_affected_rows(self):
        payload = self._execute(
            "query_database_sql",
            {
                "sql": (
                    "UPDATE processing_processrun "
                    "SET total_records = total_records WHERE id = "
                    f"{self.process_run.id}"
                )
            },
        )

        self.assertTrue(payload["meta"]["unsafe_sql_enabled"])
        self.assertIn("rows_affected", payload["meta"])
