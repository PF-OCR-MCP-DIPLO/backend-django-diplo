from django.test import SimpleTestCase

from apps.api.services.assistant_multiagent import AssistantIntent, IntentAgent, PlanningAgent


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
        intent = self._infer("Dame las referencias entre el 1 de enero y el 15 de febrero")
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
        ref_filters = [item for item in query["filters"] if item["field"] == "referencia"]
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
            messages=[{"role": "user", "content": "ahora dame el promedio de transacciones"}],
            job_id=None,
            errors=0,
        )

        self.assertEqual(intent.tool_hint, "query_database")
        self.assertIn("aggregations", intent.arguments["query"])
        self.assertEqual(intent.arguments["query"]["aggregations"][0]["type"], "avg")

        planner = PlanningAgent(model="dummy", timeout=1, provider="ollama")
        plan = planner.plan(
            intent=intent,
            messages=[{"role": "user", "content": "ahora dame el promedio de transacciones"}],
            job_id=None,
            errors=0,
        )
        self.assertEqual(plan.tool, "query_database")
        merged_filters = plan.arguments["query"].get("filters", [])
        self.assertFalse(
            any(item.get("field") == "valor" and item.get("op") == "gt" for item in merged_filters)
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
        self.assertEqual(intent.name, "unknown")  # Since followup is no longer supported
