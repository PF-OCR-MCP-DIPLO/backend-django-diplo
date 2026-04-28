from django.test import SimpleTestCase

from apps.api.services.assistant_multiagent import (
    AssistantIntent,
    AssistantPlan,
    ResponseAgent,
)


class FakeTextClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def generate(self, prompt: str, config):
        self.calls.append({"prompt": prompt, "config": config})
        return self.response


class AssistantResponseAgentTests(SimpleTestCase):
    def setUp(self):
        self.intent = AssistantIntent(name="test", confidence=1.0, summary="test")

    def _compose(self, tool: str, payload):
        agent = ResponseAgent(model="dummy", timeout=1, provider="ollama")
        plan = AssistantPlan(
            tool=tool,
            arguments={},
            intent_name="test",
            intent_summary="test",
        )
        return agent.compose(
            messages=[{"role": "user", "content": "hola"}],
            intent=self.intent,
            plan=plan,
            tool_payload=payload,
            job_id=3,
            errors=0,
        )

    def test_compose_known_tool_responses(self):
        self.assertIn(
            "creado",
            self._compose(
                "crud_database", {"operation": "create", "created_id": 10}
            ).lower(),
        )
        self.assertIn(
            "Actualicé",
            self._compose("crud_database", {"operation": "update", "updated_count": 2}),
        )
        self.assertIn(
            "Eliminé",
            self._compose("crud_database", {"operation": "delete", "deleted_count": 1}),
        )
        self.assertIn(
            "lectura",
            self._compose("crud_database", {"operation": "read"}),
        )
        self.assertIn(
            "detalle",
            self._compose("crud_database", {"detail": "detalle"}),
        )

    def test_compose_query_and_summary_responses(self):
        self.assertIn("3 jobs", self._compose("list_jobs", [{}, {}, {}]))
        self.assertIn(
            "Puedo consultar",
            self._compose(
                "describe_database_schema", {"sources": {"deposits": {}, "logs": {}}}
            ),
        )
        self.assertIn(
            "Actualmente hay 4",
            self._compose(
                "query_database",
                {
                    "source": "deposits",
                    "rows": [{"total_records": 4}],
                    "meta": {"has_aggregations": True, "rows_count": 1},
                },
            ),
        )
        self.assertIn(
            "2 resultado",
            self._compose(
                "query_database",
                {"source": "deposits", "rows": [{}, {}], "meta": {"rows_count": 2}},
            ),
        )
        self.assertEqual(
            self._compose("query_database", {"detail": "sin datos"}),
            "sin datos",
        )

    def test_compose_query_database_response_lists_key_columns(self):
        response = self._compose(
            "query_database",
            {
                "source": "deposits",
                "rows": [
                    {
                        "referencia": "REF001",
                        "fecha_consignacion": "2026-04-01",
                        "valor": "100.00",
                    },
                    {
                        "referencia": "REF002",
                        "fecha_consignacion": "2026-04-02",
                        "valor": "200.00",
                    },
                ],
                "meta": {"rows_count": 2},
            },
        )
        self.assertIn("REF001", response)
        self.assertIn("100.00", response)
        self.assertIn("Encontré 2 resultado", response)

    def test_compose_query_database_response_summarizes_many_results(self):
        response = self._compose(
            "query_database",
            {
                "source": "deposits",
                "rows": [
                    {
                        "referencia": f"REF{i}",
                        "fecha_consignacion": "2026-04-01",
                        "valor": "100.00",
                    }
                    for i in range(12)
                ],
                "meta": {"rows_count": 12},
            },
        )
        self.assertIn("primeros 10", response)
        self.assertIn("REF0", response)
        self.assertNotIn("REF11", response)

    def test_compose_sql_totals_and_last_record(self):
        self.assertIn(
            "5 resultado",
            self._compose("query_database_sql", {"meta": {"rows_count": 5}}),
        )
        self.assertEqual(
            self._compose("query_database_sql", {"detail": "sql invalido"}),
            "sql invalido",
        )
        self.assertIn(
            "123.00 COP",
            self._compose(
                "get_completed_records_summary",
                {"total_records": 2, "total_value": "123.00", "currency": "COP"},
            ),
        )
        self.assertEqual(
            self._compose("get_completed_records_summary", {"detail": "sin registros"}),
            "sin registros",
        )
        self.assertIn(
            "REF",
            self._compose(
                "get_last_record_value",
                {"job_id": 7, "last_record": {"valor": "50.00", "referencia": "REF"}},
            ),
        )
        self.assertEqual(
            self._compose("get_last_record_value", {"detail": "sin job"}),
            "sin job",
        )

    def test_compose_generic_uses_text_client_and_fallback(self):
        text_client = FakeTextClient("respuesta generada")
        agent = ResponseAgent(
            model="dummy",
            timeout=6,
            provider="anthropic",
            api_key="test-key",
            text_client=text_client,
        )
        plan = AssistantPlan(
            tool="none",
            arguments={},
            intent_name="test",
            intent_summary="test",
        )

        response = agent.compose(
            messages=[{"role": "user", "content": "hola"}],
            intent=self.intent,
            plan=plan,
            tool_payload={"kind": "none"},
            job_id=None,
            errors=0,
        )

        self.assertEqual(response, "respuesta generada")
        self.assertEqual(text_client.calls[0]["config"].provider, "anthropic")
        self.assertEqual(text_client.calls[0]["config"].api_key, "test-key")

        empty_agent = ResponseAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient(""),
        )
        fallback = empty_agent.compose(
            messages=[{"role": "user", "content": "hola"}],
            intent=self.intent,
            plan=plan,
            tool_payload={},
            job_id=None,
            errors=0,
        )
        self.assertIn("puedo ayudarte", fallback.lower())

    def test_compose_none_uses_conversational_chat(self):
        text_client = FakeTextClient("Hola, claro que sí.")
        agent = ResponseAgent(
            model="dummy",
            timeout=6,
            provider="ollama",
            text_client=text_client,
        )
        plan = AssistantPlan(
            tool="none",
            arguments={},
            intent_name="generic_chat",
            intent_summary="generic chat",
        )

        response = agent.compose(
            messages=[{"role": "user", "content": "hola"}],
            intent=self.intent,
            plan=plan,
            tool_payload={"kind": "none"},
            job_id=None,
            errors=0,
        )

        self.assertEqual(response, "Hola, claro que sí.")

    def test_compose_none_falls_back_to_helpful_copy_when_model_is_empty(self):
        empty_agent = ResponseAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient(""),
        )
        plan = AssistantPlan(
            tool="none",
            arguments={},
            intent_name="generic_chat",
            intent_summary="generic chat",
        )

        fallback = empty_agent.compose(
            messages=[{"role": "user", "content": "hola"}],
            intent=self.intent,
            plan=plan,
            tool_payload={},
            job_id=None,
            errors=0,
        )

        self.assertNotIn("herramienta no devolvió datos", fallback.lower())
        self.assertIn("puedo ayudarte", fallback.lower())

    def test_compose_capabilities_tool(self):
        response = self._compose(
            "explain_capabilities",
            {
                "title": "Puedo ayudarte con esto",
                "capabilities": ["Consultar jobs", "Exportar Excel"],
                "tools": ["list_jobs"],
            },
        )
        self.assertIn("Consultar jobs", response)
