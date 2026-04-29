import asyncio
import json
import os
import tempfile
from unittest.mock import patch

import requests
from django.test import TestCase, override_settings

from mcp_server import server
from mcp_server.api_client import BackendApiClient, BackendApiError


class DummyResponse:
    def __init__(
        self,
        status_code,
        payload=None,
        *,
        text="",
        content=None,
        json_error=False,
    ):
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self._payload = payload
        self.text = text
        self.content = (
            content
            if content is not None
            else (b"" if payload is None and not text else b"{}")
        )
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


class McpContractTests(TestCase):
    """Protege que las herramientas MCP mantengan un contrato JSON estable."""

    def test_all_mcp_tools_return_json_object(self):
        payload = json.loads(server.health_check())
        self.assertIn("ok", payload)
        self.assertIn("data", payload)
        self.assertIn("status_code", payload)
        self.assertIn("detail", payload)

    def test_assistant_chat_tool_returns_json_object(self):
        payload = json.loads(
            server.assistant_chat(
                messages=[{"role": "user", "content": "hola"}],
                query_context={"scope": "results"},
            )
        )

        self.assertIn("ok", payload)
        self.assertIn("data", payload)
        self.assertIn("status_code", payload)
        self.assertEqual(payload["status_code"], 200)

    @override_settings(MCP_ENABLE_MUTATIONS=False)
    def test_reprocess_failed_sources_blocked_when_mutations_disabled(self):
        payload = json.loads(server.reprocess_failed_sources(1))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status_code"], 403)
        self.assertIsNone(payload["data"])

    @override_settings(MCP_ENABLE_MUTATIONS=False)
    def test_all_mutating_tools_are_blocked_when_mutations_disabled(self):
        outputs = [
            server.upload_document("/tmp/test.docx"),
            server.process_job(1),
            server.reprocess_failed_sources(1),
            server.reprocess_source_image(1, source_image_id=1),
            server.export_job_excel(1),
            server.update_deposit_correction(1, 1, "REF001", 1000),
            server.update_processing_settings(ocr_model="spa"),
            server.crud_database("delete", "deposits"),
        ]

        for raw_output in outputs:
            payload = json.loads(raw_output)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["status_code"], 403)
            self.assertEqual(payload["code"], "mutation_disabled")
            self.assertIsNone(payload["data"])

    @override_settings(MCP_ENABLE_MUTATIONS=False)
    def test_read_only_tools_do_not_require_mutation_toggle(self):
        payload = json.loads(server.list_jobs())

        self.assertTrue(payload["ok"])
        self.assertIn("data", payload)

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_pydantic_errors_are_controlled_json(self):
        payload = json.loads(server.process_job(0))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status_code"], 400)
        self.assertEqual(payload["detail"], "validation_error")
        self.assertEqual(payload["code"], "validation_error")
        self.assertNotIn("Traceback", json.dumps(payload))

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_reprocess_source_requires_explicit_target(self):
        payload = json.loads(server.reprocess_source_image(1))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status_code"], 400)
        self.assertEqual(payload["detail"], "validation_error")

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_upload_document_rejects_unsafe_paths(self):
        relative = json.loads(server.upload_document("relative.docx"))
        self.assertFalse(relative["ok"])
        self.assertEqual(relative["status_code"], 400)

        wrong_extension = json.loads(server.upload_document("/tmp/not-docx.txt"))
        self.assertFalse(wrong_extension["ok"])
        self.assertEqual(wrong_extension["status_code"], 400)

        with tempfile.TemporaryDirectory() as allowed_root:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                with override_settings(MCP_ALLOWED_UPLOAD_ROOTS=[allowed_root]):
                    outside = json.loads(server.upload_document(tmp_path))
                self.assertFalse(outside["ok"])
                self.assertEqual(outside["status_code"], 400)
                self.assertIn("allowed upload roots", json.dumps(outside))
            finally:
                os.unlink(tmp_path)

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_upload_document_allows_null_data_success_envelope(self):
        with patch(
            "mcp_server.server.upload_document_from_path",
            return_value=None,
        ):
            payload = json.loads(server.upload_document("/tmp/test.docx"))

        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["data"])

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_update_processing_settings_does_not_leak_secrets(self):
        with patch(
            "mcp_server.server.execute_tool",
            return_value={
                "assistant_api_key": "SECRET-ASSISTANT",
                "nested": {"ocr_api_key": "SECRET-OCR"},
            },
        ):
            raw_output = server.update_processing_settings(
                assistant_api_key="SECRET-ASSISTANT",
                ocr_api_key="SECRET-OCR",
            )

        self.assertNotIn("SECRET-ASSISTANT", raw_output)
        self.assertNotIn("SECRET-OCR", raw_output)
        payload = json.loads(raw_output)
        self.assertEqual(payload["data"]["assistant_api_key"], "***")

    def test_mcp_annotations_resources_and_prompts_are_exposed(self):
        async def collect():
            return (
                await server.mcp.list_tools(),
                await server.mcp.list_resources(),
                await server.mcp.list_resource_templates(),
                await server.mcp.list_prompts(),
            )

        tools, resources, resource_templates, prompts = asyncio.run(collect())
        tools_by_name = {tool.name: tool for tool in tools}

        self.assertTrue(tools_by_name["list_jobs"].annotations.readOnlyHint)
        self.assertFalse(tools_by_name["process_job"].annotations.readOnlyHint)
        self.assertTrue(
            tools_by_name["update_deposit_correction"].annotations.destructiveHint
        )
        self.assertIn("diplo://health", {str(resource.uri) for resource in resources})
        self.assertIn(
            "diplo://jobs/{job_id}",
            {template.uriTemplate for template in resource_templates},
        )
        self.assertIn("diagnose_job", {prompt.name for prompt in prompts})

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_reprocess_failed_sources_returns_standard_json(self):
        with patch("mcp_server.server.execute_tool", return_value={"id": 1}):
            payload = json.loads(server.reprocess_failed_sources(1))

        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["status_code"])
        self.assertEqual(payload["data"], {"id": 1})
        self.assertIsNone(payload["detail"])


class BackendApiClientContractTests(TestCase):
    """Cubre el cliente HTTP legacy que puede usarse como fallback MCP."""

    def test_handles_success_json_and_empty_2xx(self):
        client = BackendApiClient(base_url="http://backend.test/api")

        self.assertEqual(
            client._handle_response(DummyResponse(200, {"status": "ok"})),
            {"status": "ok"},
        )
        self.assertEqual(
            client._handle_response(DummyResponse(204, content=b"")),
            {},
        )

    def test_handles_error_json_and_plain_error(self):
        client = BackendApiClient(base_url="http://backend.test/api")

        with self.assertRaises(BackendApiError) as json_error:
            client._handle_response(
                DummyResponse(
                    409,
                    {"error": {"message": "Ya se esta procesando"}},
                )
            )
        self.assertEqual(json_error.exception.status_code, 409)
        self.assertEqual(json_error.exception.detail, "Ya se esta procesando")

        with self.assertRaises(BackendApiError) as text_error:
            client._handle_response(
                DummyResponse(500, text="server exploded", json_error=True)
            )
        self.assertEqual(text_error.exception.status_code, 500)
        self.assertEqual(text_error.exception.detail, "server exploded")

    def test_request_timeout_and_api_key_header_are_controlled(self):
        client = BackendApiClient(
            base_url="http://backend.test/api",
            api_token="secret-token",
        )

        with patch(
            "mcp_server.api_client.requests.request",
            side_effect=requests.Timeout,
        ):
            with self.assertRaises(BackendApiError) as timeout_error:
                client.get_health()
        self.assertEqual(timeout_error.exception.status_code, 504)

        with patch("mcp_server.api_client.requests.request") as mocked_request:
            mocked_request.return_value = DummyResponse(200, {"status": "ok"})
            self.assertEqual(client.get_health(), {"status": "ok"})

        self.assertEqual(
            mocked_request.call_args.kwargs["headers"]["X-API-Key"],
            "secret-token",
        )
