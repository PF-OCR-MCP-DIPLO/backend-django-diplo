import json
from django.test import TestCase

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
