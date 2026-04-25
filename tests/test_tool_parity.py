import json

from django.test import TestCase

from mcp_server import server as mcp_server


class ToolParityTests(TestCase):
    def test_assistant_chat_preserves_contract_shape(self):
        payload = json.loads(
            mcp_server.assistant_chat(
                messages=[{"role": "user", "content": "hola"}],
                query_context={"scope": "results"},
            )
        )

        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertIn("reply", data)
        self.assertIn("message", data)
        self.assertIn("tool", data)
        self.assertIn("data", data)
        self.assertIn("query_context", data)
        self.assertEqual(data["query_context"], {"scope": "results"})
