import json
from django.test import SimpleTestCase

from mcp_server import server


class McpContractTests(SimpleTestCase):
    def test_all_mcp_tools_return_json_object(self):
        payload = json.loads(server.health_check())
        self.assertIn("ok", payload)
        self.assertIn("data", payload)
        self.assertIn("status_code", payload)
        self.assertIn("detail", payload)
