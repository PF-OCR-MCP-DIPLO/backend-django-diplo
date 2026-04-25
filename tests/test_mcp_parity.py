import json
import os
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.api.services.assistant_multiagent import AssistantPlan, ToolExecutionAgent
from mcp_server import server as mcp_server
from tests.test_api import PNG_ONE, PNG_TWO, build_docx_with_images


class McpParityTests(TestCase):
    def setUp(self):
        self.executor = ToolExecutionAgent()
        self.docx_bytes = build_docx_with_images(
            {"image1.png": PNG_ONE, "image2.png": PNG_TWO}
        )

    def _multiagent_payload(
        self, tool: str, arguments: dict | None = None, job_id: int | None = None
    ):
        plan = AssistantPlan(
            tool=tool,
            arguments=arguments or {},
            intent_name="test",
            intent_summary="parity",
        )
        return self.executor.execute(plan, job_id=job_id)

    def _mcp_payload(self, raw_output: str):
        envelope = json.loads(raw_output)
        self.assertTrue(envelope.get("ok"), envelope)
        return envelope["data"]

    def test_basic_tools_match_multiagent(self):
        self.assertEqual(
            self._mcp_payload(mcp_server.health_check()),
            self._multiagent_payload("health_check"),
        )
        self.assertEqual(
            self._mcp_payload(mcp_server.list_jobs()),
            self._multiagent_payload("list_jobs"),
        )
        self.assertEqual(
            self._mcp_payload(mcp_server.get_processing_settings()),
            self._multiagent_payload("get_processing_settings"),
        )
        self.assertEqual(
            self._mcp_payload(mcp_server.get_processing_settings_options()),
            self._multiagent_payload("get_processing_settings_options"),
        )

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_deposit_correction_tool_matches_multiagent(self):
        payload = {
            "job_id": 10,
            "deposit_id": 11,
            "fecha_consignacion": "2026-04-23",
            "hora_consignacion": "10:00",
            "referencia": "REFMCP001",
            "valor": 1000,
        }
        self.assertEqual(
            self._mcp_payload(mcp_server.update_deposit_correction(**payload)),
            self._multiagent_payload("update_deposit_correction", payload, job_id=10),
        )

    def test_mutation_tool_is_blocked_when_disabled(self):
        envelope = json.loads(mcp_server.process_job(1))
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["status_code"], 403)

    def test_upload_and_status_match_multiagent(self):
        tmp_path = ""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(self.docx_bytes)
            tmp.flush()
            tmp_path = tmp.name
        try:
            mcp_uploaded = self._mcp_payload(mcp_server.upload_document(tmp_path))
            mcp_job_id = mcp_uploaded["id"]

            ma_uploaded = self._multiagent_payload(
                "upload_document", {"file_path": tmp_path}
            )
            ma_job_id = ma_uploaded["id"]

            self.assertEqual(mcp_uploaded["total_images"], ma_uploaded["total_images"])
            self.assertEqual(
                mcp_uploaded["original_filename"], ma_uploaded["original_filename"]
            )

            self.assertEqual(
                self._mcp_payload(mcp_server.get_job_status(mcp_job_id)),
                self._multiagent_payload(
                    "get_job_status", {"job_id": mcp_job_id}, job_id=mcp_job_id
                ),
            )
            self.assertEqual(
                self._mcp_payload(mcp_server.get_job_status(ma_job_id)),
                self._multiagent_payload(
                    "get_job_status", {"job_id": ma_job_id}, job_id=ma_job_id
                ),
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_log_alias_returns_same_payload(self):
        tmp_path = ""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(self.docx_bytes)
            tmp.flush()
            tmp_path = tmp.name
        try:
            uploaded = self._mcp_payload(mcp_server.upload_document(tmp_path))
            job_id = uploaded["id"]

            with (
                patch(
                    "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                    side_effect=["OCR 1", "OCR 2"],
                ),
                patch(
                    "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                    side_effect=[[], []],
                ),
            ):
                _ = self._mcp_payload(mcp_server.process_job(job_id))

            canonical = self._mcp_payload(mcp_server.get_job_logs(job_id))
            alias = self._mcp_payload(mcp_server.list_job_logs(job_id))
            self.assertEqual(alias, canonical)
            self.assertEqual(
                canonical,
                self._multiagent_payload(
                    "get_job_logs", {"job_id": job_id}, job_id=job_id
                ),
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
