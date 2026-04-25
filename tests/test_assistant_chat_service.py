from django.test import TestCase

from apps.api.services.assistant_chat import AssistantChatService
from apps.api.services.assistant_llm import AssistantProviderError
from apps.api.services.assistant_multiagent import (
    AssistantAgent,
    AssistantIntent,
    AssistantPlan,
)


class FakeAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def answer(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class BrokenAgent:
    def answer(self, **kwargs):
        raise RuntimeError("boom")


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

    def test_answer_keeps_empty_query_context_when_missing(self):
        agent = FakeAgent({"reply": "ok"})
        service = AssistantChatService(agent_factory=lambda: agent)

        response = service.answer(
            {"messages": [{"role": "user", "content": "hola"}], "query_context": None}
        )

        self.assertEqual(response["query_context"], {})

    def test_answer_converts_missing_or_invalid_query_context_to_empty_dict(self):
        agent = FakeAgent({"reply": "ok"})
        service = AssistantChatService(agent_factory=lambda: agent)

        response = service.answer(
            {"messages": [{"role": "user", "content": "hola"}], "query_context": []}
        )

        self.assertEqual(response["query_context"], {})
        self.assertEqual(agent.calls[0]["query_context"], {})

    def test_answer_returns_controlled_fallback_when_agent_raises(self):
        service = AssistantChatService(agent_factory=lambda: BrokenAgent())

        response = service.answer(
            {
                "messages": [{"role": "user", "content": "hola"}],
                "query_context": {"scope": "results"},
            }
        )

        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["data"]["detail"], "assistant_unavailable")
        self.assertEqual(response["query_context"], {"scope": "results"})
        self.assertTrue(response["debug"]["fallback_used"])

    def test_finalize_response_hides_technical_error_details_by_default(self):
        service = AssistantChatService(agent_factory=lambda: FakeAgent({"reply": "ok"}))

        response = service.finalize_response(
            {
                "reply": "No disponible",
                "tool": "none",
                "data": {
                    "detail": "assistant_provider_error",
                    "error": "traceback interno",
                },
                "debug": {"errors": ["traceback interno"]},
                "query_context": {},
            },
            show_debug_details=False,
        )

        self.assertEqual(response["data"]["detail"], "assistant_provider_error")
        self.assertNotIn("error", response["data"])
        self.assertEqual(response["debug"]["errors"], [])

    def test_finalize_response_keeps_technical_error_details_when_debug_is_enabled(self):
        service = AssistantChatService(agent_factory=lambda: FakeAgent({"reply": "ok"}))

        response = service.finalize_response(
            {
                "reply": "No disponible",
                "tool": "none",
                "data": {
                    "detail": "assistant_provider_error",
                    "error": "detalle tecnico",
                },
                "debug": {"errors": ["detalle tecnico"]},
                "query_context": {},
            },
            show_debug_details=True,
        )

        self.assertEqual(response["data"]["error"], "detalle tecnico")
        self.assertEqual(response["debug"]["errors"], ["detalle tecnico"])

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
        agent.response_agent.compose = lambda *args, **kwargs: "Procesamiento iniciado."

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
        self.assertEqual(
            response["message"], "De acuerdo, cancelé la acción pendiente."
        )
        self.assertNotIn("pending_action", response["query_context"])

    def test_assistant_agent_requests_confirmation_for_deposit_correction(self):
        agent = AssistantAgent()
        agent.intent_agent.infer = lambda *args, **kwargs: AssistantIntent(
            name="deposit_correction",
            confidence=0.99,
            tool_hint="update_deposit_correction",
            summary="corregir fila",
        )
        agent.planner_agent.plan = lambda *args, **kwargs: AssistantPlan(
            tool="update_deposit_correction",
            arguments={
                "job_id": 12,
                "deposit_id": 44,
                "referencia": "R1",
                "valor": 100,
            },
            intent_name="deposit_correction",
            intent_summary="corregir fila",
        )
        agent.tool_agent.execute = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("tool executor should not run before confirmation")
        )

        response = agent.answer(
            messages=[{"role": "user", "content": "corrige la fila 44"}],
            job_id=12,
            errors=0,
        )

        self.assertEqual(response["tool"], "update_deposit_correction")
        self.assertTrue(response["data"]["requires_confirmation"])
        self.assertIn("fila", response["message"].lower())

    def test_assistant_agent_asks_for_clarification_when_correction_is_incomplete(self):
        agent = AssistantAgent()
        agent.intent_agent.infer = lambda *args, **kwargs: AssistantIntent(
            name="deposit_correction",
            confidence=0.99,
            tool_hint="update_deposit_correction",
            summary="corregir fila",
            arguments={"job_id": 12},
        )
        agent.planner_agent.plan = lambda *args, **kwargs: AssistantPlan(
            tool="update_deposit_correction",
            arguments={"job_id": 12},
            intent_name="deposit_correction",
            intent_summary="corregir fila",
        )
        agent.tool_agent.execute = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("tool executor should not run when data is incomplete")
        )

        response = agent.answer(
            messages=[{"role": "user", "content": "corrige esta fila"}],
            job_id=12,
            errors=0,
        )

        self.assertEqual(response["tool"], "none")
        self.assertTrue(response["data"]["requires_clarification"])
        self.assertIn("necesito", response["message"].lower())

    def test_assistant_agent_revalidates_pending_action_before_execution(self):
        agent = AssistantAgent()

        response = agent.answer(
            messages=[{"role": "user", "content": "confirmar"}],
            job_id=12,
            query_context={
                "pending_action": {
                    "id": "stale-action",
                    "tool": "update_deposit_correction",
                    "label": "Corregir consignación",
                    "summary": "corregir fila",
                    "risk": "requires_confirmation",
                    "arguments": {"job_id": 12},
                }
            },
        )

        self.assertEqual(response["tool"], "none")
        self.assertTrue(response["data"]["requires_clarification"])
        self.assertNotIn("pending_action", response["query_context"])

    def test_assistant_agent_does_not_raise_name_error_when_runtime_sync_fails(self):
        agent = AssistantAgent()
        agent._sync_runtime_model = lambda: (_ for _ in ()).throw(RuntimeError("sync failed"))

        response = agent.answer(
            messages=[{"role": "user", "content": "hola"}],
            query_context={"scope": "results"},
        )

        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["data"]["detail"], "assistant_unavailable")
        self.assertEqual(response["query_context"], {"scope": "results"})

    def test_assistant_agent_handles_provider_memory_error_with_recommendation(self):
        agent = AssistantAgent()
        agent.intent_agent.infer = lambda *args, **kwargs: AssistantIntent(
            name="generic_chat",
            confidence=0.8,
            tool_hint="none",
            summary="chat",
        )
        agent.planner_agent.plan = lambda *args, **kwargs: AssistantPlan(
            tool="none",
            arguments={},
            intent_name="generic_chat",
            intent_summary="chat",
        )

        def _raise(*args, **kwargs):
            raise AssistantProviderError(
                provider="ollama",
                message="El modelo no cabe en memoria.",
                detail="model requires more system memory (5.4 GiB) than is available (5.2 GiB)",
                status_code=500,
                code="assistant_model_too_large",
            )

        agent.response_agent.compose = _raise

        response = agent.answer(
            messages=[{"role": "user", "content": "hola"}],
            query_context={},
        )

        self.assertEqual(response["tool"], "none")
        self.assertEqual(response["data"]["detail"], "assistant_model_too_large")
        self.assertIn("qwen3:1.7b", response["message"])
