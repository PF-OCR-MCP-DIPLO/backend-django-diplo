from django.test import SimpleTestCase

from apps.api.services.assistant_chat import AssistantChatService


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def answer(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class AssistantChatServiceTests(SimpleTestCase):
    def test_answer_delegates_to_agent_and_preserves_query_context(self):
        agent = FakeAgent({"reply": "ok", "tool": "query_database", "data": []})
        service = AssistantChatService(agent_factory=lambda: agent)

        response = service.answer(
            {
                "messages": [{"role": "user", "content": "hola"}],
                "job_id": 5,
                "errors": 1,
                "query_context": {"scope": "results"},
            }
        )

        self.assertEqual(response["reply"], "ok")
        self.assertEqual(response["tool"], "query_database")
        self.assertEqual(response["data"], [])
        self.assertEqual(response["query_context"], {"scope": "results"})
        self.assertEqual(
            agent.calls,
            [
                {
                    "messages": [{"role": "user", "content": "hola"}],
                    "job_id": 5,
                    "errors": 1,
                }
            ],
        )

    def test_answer_normalizes_unexpected_agent_payload(self):
        agent = FakeAgent("respuesta sin estructura")
        service = AssistantChatService(agent_factory=lambda: agent)

        response = service.answer(
            {"messages": [{"role": "user", "content": "hola"}], "query_context": {}}
        )

        self.assertEqual(response["reply"], "respuesta sin estructura")
        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["data"], {})
        self.assertEqual(response["query_context"], {})
