from django.test import SimpleTestCase

from apps.api.services.assistant_multiagent import (
    AssistantIntent,
    AssistantPlan,
    IntentAgent,
    PlanningAgent,
)


class FakeTextClient:
    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls = []

    def generate(self, prompt: str, config):
        self.calls.append({"prompt": prompt, "config": config})
        return self.responses.pop(0) if self.responses else ""


class AssistantIntentQueryTests(SimpleTestCase):
    def setUp(self):
        self.agent = IntentAgent(model="dummy", timeout=1, provider="ollama")

    def _infer(self, message: str):
        return self.agent.infer(
            messages=[{"role": "user", "content": message}],
            job_id=None,
            errors=0,
        )

    def test_latest_transactions_with_limit(self):
        intent = self._infer("Lista las ultimas 10 transacciones")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["limit"], 10)
        self.assertEqual(query["order_by"][0]["field"], "created_at")
        self.assertEqual(query["order_by"][0]["direction"], "desc")

    def test_range_and_references_query(self):
        intent = self._infer(
            "Dame las referencias entre el 1 de enero y el 15 de febrero"
        )
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertIn("referencia", query["select"])
        ops = {item["op"] for item in query["filters"]}
        self.assertIn("date_gte", ops)
        self.assertIn("date_lte", ops)

    def test_last_month_and_amount_filter(self):
        intent = self._infer("Dame las transacciones del ultimo mes mayores a $100.000")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        ops = {item["op"] for item in query["filters"]}
        self.assertIn("in_last_days", ops)
        self.assertIn("gt", ops)

    def test_sum_current_month(self):
        intent = self._infer("Suma de transacciones del ultimo mes")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["aggregations"][0]["type"], "sum")
        self.assertEqual(query["aggregations"][0]["field"], "valor")

    def test_reference_lookup(self):
        intent = self._infer("Busca la transaccion con referencia ABC12345")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        ref_filters = [
            item for item in query["filters"] if item["field"] == "referencia"
        ]
        self.assertTrue(ref_filters)
        self.assertEqual(ref_filters[0]["op"], "icontains")

    def test_near_amount_lookup(self):
        intent = self._infer("Encuentra una transaccion cercana a $200.000")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        between_filters = [item for item in query["filters"] if item["op"] == "between"]
        self.assertTrue(between_filters)
        self.assertEqual(between_filters[0]["field"], "valor")

    def test_followup_with_new_explicit_query_does_not_repeat_previous_one(self):
        previous_context = {
            "query": {
                "source": "deposits",
                "filters": [{"field": "valor", "op": "gt", "value": 500000}],
                "order_by": [{"field": "created_at", "direction": "desc"}],
                "limit": 30,
            }
        }

        intent = self.agent.infer(
            messages=[
                {"role": "user", "content": "ahora dame el promedio de transacciones"}
            ],
            job_id=None,
            errors=0,
        )

        self.assertEqual(intent.tool_hint, "query_database")
        self.assertIn("aggregations", intent.arguments["query"])
        self.assertEqual(intent.arguments["query"]["aggregations"][0]["type"], "avg")

        planner = PlanningAgent(model="dummy", timeout=1, provider="ollama")
        plan = planner.plan(
            intent=intent,
            messages=[
                {"role": "user", "content": "ahora dame el promedio de transacciones"}
            ],
            job_id=None,
            errors=0,
        )
        self.assertEqual(plan.tool, "query_database")
        merged_filters = plan.arguments["query"].get("filters", [])
        self.assertFalse(
            any(
                item.get("field") == "valor" and item.get("op") == "gt"
                for item in merged_filters
            )
        )

    def test_true_followup_without_new_query_is_rejected(self):
        previous_context = {
            "query": {
                "source": "deposits",
                "filters": [{"field": "valor", "op": "gt", "value": 100000}],
                "order_by": [{"field": "created_at", "direction": "desc"}],
                "limit": 20,
            }
        }
        intent = self.agent._infer_direct_intent(
            text="ahora solo esas",
            job_id=None,
        )
        self.assertIsNotNone(intent)
        assert isinstance(intent, AssistantIntent)
        self.assertEqual(
            intent.name, "unknown"
        )  # Since followup is no longer supported

    def test_infer_without_user_message_returns_unknown(self):
        intent = self.agent.infer(messages=[], job_id=None, errors=0)

        self.assertEqual(intent.name, "unknown")
        self.assertEqual(intent.confidence, 0.0)

    def test_llm_infer_parses_json_and_injects_job_id(self):
        text_client = FakeTextClient("""```json
            {
              "intent": "job_status",
              "tool_hint": "get_job_status",
              "confidence": 0.81,
              "summary": "estado",
              "arguments": {}
            }
            ```""")
        agent = IntentAgent(
            model="dummy",
            timeout=3,
            provider="anthropic",
            api_key="test-key",
            text_client=text_client,
        )

        intent = agent.infer(
            messages=[{"role": "user", "content": "puedes ayudarme?"}],
            job_id=99,
            errors=4,
        )

        self.assertEqual(intent.name, "job_status")
        self.assertEqual(intent.tool_hint, "get_job_status")
        self.assertEqual(intent.arguments["job_id"], 99)
        self.assertEqual(text_client.calls[0]["config"].provider, "anthropic")
        self.assertEqual(text_client.calls[0]["config"].api_key, "test-key")

    def test_llm_infer_invalid_payload_returns_unknown(self):
        agent = IntentAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient("not json"),
        )

        intent = agent.infer(
            messages=[{"role": "user", "content": "ayuda general"}],
            job_id=None,
            errors=0,
        )

        self.assertEqual(intent.name, "unknown")
        self.assertIsNone(intent.tool_hint)


class AssistantPlanningTests(SimpleTestCase):
    def test_plan_uses_tool_hint_without_llm_call(self):
        planner = PlanningAgent(model="dummy", timeout=1, provider="ollama")
        intent = AssistantIntent(
            name="job_logs",
            confidence=0.9,
            tool_hint="get_job_logs",
            summary="logs",
        )

        plan = planner.plan(
            intent=intent,
            messages=[{"role": "user", "content": "logs"}],
            job_id=8,
            errors=0,
        )

        self.assertEqual(plan.tool, "get_job_logs")
        self.assertEqual(plan.arguments["job_id"], 8)

    def test_plan_parses_llm_json_and_normalizes_query_arguments(self):
        planner = PlanningAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient(
                '{"tool": "query_database", "arguments": {"query": null}}'
            ),
        )
        intent = AssistantIntent(name="generic", confidence=0.1, summary="generic")

        plan = planner.plan(
            intent=intent,
            messages=[{"role": "user", "content": "consulta"}],
            job_id=4,
            errors=0,
        )

        self.assertEqual(plan.tool, "query_database")
        self.assertEqual(plan.arguments["job_id"], 4)
        self.assertEqual(plan.arguments["query"], {})

    def test_plan_rejects_invalid_llm_output(self):
        planner = PlanningAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient("not json"),
        )
        intent = AssistantIntent(name="generic", confidence=0.1, summary="generic")

        plan = planner.plan(
            intent=intent,
            messages=[{"role": "user", "content": "consulta"}],
            job_id=None,
            errors=0,
        )

        self.assertEqual(plan.tool, "none")
        self.assertEqual(plan.arguments, {})

    def test_plan_rejects_unknown_tool(self):
        planner = PlanningAgent(
            model="dummy",
            timeout=1,
            provider="ollama",
            text_client=FakeTextClient('{"tool": "drop_database", "arguments": []}'),
        )
        intent = AssistantIntent(name="generic", confidence=0.1, summary="generic")

        plan = planner.plan(
            intent=intent,
            messages=[{"role": "user", "content": "consulta"}],
            job_id=None,
            errors=0,
        )

        self.assertIsInstance(plan, AssistantPlan)
        self.assertEqual(plan.tool, "none")
        self.assertEqual(plan.arguments, {})
