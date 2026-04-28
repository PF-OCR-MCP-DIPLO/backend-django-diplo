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

    def test_all_transactions_query(self):
        intent = self._infer("Muéstrame todas las transacciones")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["limit"], 200)
        self.assertEqual(query["order_by"][0]["field"], "created_at")
        self.assertEqual(query["order_by"][0]["direction"], "desc")

    def test_all_month_values_query(self):
        intent = self._infer("Muéstrame todos los valores del mes")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["limit"], 200)
        self.assertTrue(any(f["op"] in {"date_gte", "date_lte", "in_last_days"} for f in query["filters"]))

    def test_followup_valor_de_todos_uses_last_query_context(self):
        existing_query = {
            "source": "deposits",
            "filters": [{"field": "created_at", "op": "in_last_days", "value": 30}],
            "order_by": [{"field": "created_at", "direction": "desc"}],
            "limit": 200,
        }
        intent = self.agent.infer(
            messages=[{"role": "user", "content": "Muéstrame el valor de todos"}],
            job_id=None,
            errors=0,
            query_context={"last_query": existing_query},
        )
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["select"], ["referencia", "fecha_consignacion", "valor"])
        self.assertEqual(query["filters"], existing_query["filters"])
        self.assertEqual(query["order_by"], existing_query["order_by"])
        self.assertEqual(query["limit"], 200)

    def test_followup_no_longer_returns_last_record_value(self):
        existing_query = {
            "source": "deposits",
            "filters": [{"field": "created_at", "op": "in_last_days", "value": 30}],
            "order_by": [{"field": "created_at", "direction": "desc"}],
            "limit": 200,
        }
        intent = self.agent.infer(
            messages=[{"role": "user", "content": "Muestra su valor"}],
            job_id=None,
            errors=0,
            query_context={"last_query": existing_query},
        )
        self.assertEqual(intent.tool_hint, "query_database")
        self.assertNotEqual(intent.tool_hint, "get_last_record_value")

    def test_highest_value_transaction(self):
        intent = self._infer("Cuál es la transacción de mayor valor")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["limit"], 1)
        self.assertEqual(query["order_by"][0]["field"], "valor")
        self.assertEqual(query["order_by"][0]["direction"], "desc")

    def test_lowest_value_transaction(self):
        intent = self._infer("Y si quiero el registro de menor valor")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["limit"], 1)
        self.assertEqual(query["order_by"][0]["field"], "valor")
        self.assertEqual(query["order_by"][0]["direction"], "asc")

    def test_current_month_transactions(self):
        intent = self._infer("Transacciones del mes actual")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertTrue(any(f["op"] in {"date_gte", "date_lte"} for f in query["filters"]))

    def test_previous_month_transactions(self):
        intent = self._infer("Cuáles fueron las transacciones del mes anterior?")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertTrue(any(f["op"] == "date_gte" for f in query["filters"]))
        self.assertTrue(any(f["op"] == "date_lte" for f in query["filters"]))
        self.assertTrue(
            any(
                f["field"] == "fecha_consignacion" for f in query["filters"]
            )
        )

    def test_specific_month_transactions(self):
        intent = self._infer("Transacciones de abril 2026")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertTrue(any(f["op"] == "date_gte" for f in query["filters"]))
        self.assertTrue(any(f["op"] == "date_lte" for f in query["filters"]))

    def test_last_month_total_value(self):
        intent = self._infer("Total del valor de las transacciones del último mes")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertEqual(query["aggregations"][0]["type"], "sum")
        self.assertEqual(query["aggregations"][0]["field"], "valor")
        self.assertTrue(any(f["op"] == "in_last_days" for f in query["filters"]))

    def test_error_transactions_by_observation(self):
        intent = self._infer("Qué transacciones tienen error en fecha")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        observation_filters = [
            f for f in query["filters"] if f["field"] == "observations"
        ]
        self.assertTrue(observation_filters)
        self.assertEqual(observation_filters[0]["op"], "icontains")
        self.assertIn("fecha", observation_filters[0]["value"])

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

    def test_deposit_synonyms_match_transaction_queries(self):
        intent = self._infer("Dame las consignaciones con error en fecha")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        observation_filters = [
            item for item in query["filters"] if item["field"] == "observations"
        ]
        self.assertTrue(observation_filters)
        self.assertIn("fecha", observation_filters[0]["value"])
        self.assertIn("observations", query["select"])

    def test_error_transactions_include_observations_in_select(self):
        intent = self._infer("Muestrame transacciones con errores de valor")
        self.assertEqual(intent.tool_hint, "query_database")
        query = intent.arguments["query"]
        self.assertEqual(query["source"], "deposits")
        self.assertIn("observations", query["select"])
        observation_filters = [
            item for item in query["filters"] if item["field"] == "observations"
        ]
        self.assertTrue(observation_filters)

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
