import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from mcp_server import server


class McpContractTests(TestCase):
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

    def test_reprocess_failed_sources_blocked_when_mutations_disabled(self):
        payload = json.loads(server.reprocess_failed_sources(1))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status_code"], 403)
        self.assertIsNone(payload["data"])

    @override_settings(MCP_ENABLE_MUTATIONS=True)
    def test_reprocess_failed_sources_returns_standard_json(self):
        with patch("mcp_server.server.execute_tool", return_value={"id": 1}):
            payload = json.loads(server.reprocess_failed_sources(1))

        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["status_code"])
        self.assertEqual(payload["data"], {"id": 1})
        self.assertIsNone(payload["detail"])
