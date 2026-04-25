from django.test import TestCase

from apps.api.services.assistant_chat import AssistantChatService


class AssistantContractTests(TestCase):
    def test_general_chat_preserves_query_context(self):
        class FakeAgent:
            def answer(self, **kwargs):
                return {
                    "reply": "ok",
                    "query_context": kwargs["query_context"],
                    "tool": "none",
                    "data": {},
                }

        service = AssistantChatService(agent_factory=lambda: FakeAgent())
        response = service.answer(
            {
                "messages": [{"role": "user", "content": "hola"}],
                "query_context": {"jobId": 1},
            }
        )
        self.assertEqual(response["query_context"], {"jobId": 1})
        self.assertIn("used_context", response)
        self.assertIn("debug", response)
