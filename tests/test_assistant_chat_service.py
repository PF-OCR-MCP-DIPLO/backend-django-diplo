from django.test import TestCase

from apps.api.services.assistant_chat import AssistantChatService
from apps.api.services.assistant_multiagent import AssistantAgent, AssistantIntent, AssistantPlan


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def answer(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class AssistantChatServiceTests(TestCase):
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
        self.assertEqual(response["message"], "ok")
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
                    "query_context": {"scope": "results"},
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
        self.assertEqual(response["message"], "respuesta sin estructura")
        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["data"], {})
        self.assertEqual(response["query_context"], {})

    def test_assistant_agent_requests_confirmation_for_sensitive_tools(self):
        agent = AssistantAgent()
        agent.intent_agent.infer = lambda *args, **kwargs: AssistantIntent(
            name="process_job",
            confidence=0.99,
            tool_hint="process_job",
            summary="procesar",
        )
        agent.planner_agent.plan = lambda *args, **kwargs: AssistantPlan(
            tool="process_job",
            arguments={"job_id": 12},
            intent_name="process_job",
            intent_summary="procesar",
        )
        agent.tool_agent.execute = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("tool executor should not run before confirmation")
        )

        response = agent.answer(
            messages=[{"role": "user", "content": "procesa el job"}],
            job_id=12,
            errors=0,
        )

        self.assertEqual(response["tool"], "process_job")
        self.assertTrue(response["data"]["requires_confirmation"])
        self.assertIn("confirmacion", response["message"].lower())

    def test_assistant_agent_executes_pending_action_after_confirmation(self):
        agent = AssistantAgent()
        agent.tool_agent.execute = lambda plan, job_id=None: {
            "status": "queued",
            "tool": plan.tool,
            "job_id": job_id,
        }

        response = agent.answer(
            messages=[{"role": "user", "content": "confirmar"}],
            job_id=12,
            query_context={
                "pending_action": {
                    "tool": "process_job",
                    "arguments": {"job_id": 12},
                    "intent_name": "process_job",
                    "intent_summary": "procesar",
                    "job_id": 12,
                }
            },
        )

        self.assertEqual(response["tool"], "process_job")
        self.assertEqual(response["data"]["status"], "queued")
        self.assertNotIn("pending_action", response["query_context"])

    def test_assistant_agent_cancels_pending_action(self):
        agent = AssistantAgent()

        response = agent.answer(
            messages=[{"role": "user", "content": "cancelar"}],
            job_id=12,
            query_context={
                "pending_action": {
                    "tool": "export_job_excel",
                    "arguments": {"job_id": 12},
                    "intent_name": "prepare_export",
                    "intent_summary": "exportar",
                    "job_id": 12,
                }
            },
        )

        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["message"], "De acuerdo, cancelé la acción pendiente.")
        self.assertNotIn("pending_action", response["query_context"])
