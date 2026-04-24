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
        self.assertIn("No pude generar", fallback)
