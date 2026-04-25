from django.test import SimpleTestCase, override_settings

from apps.processing.services.ollama_models import get_available_models, list_installed_models


class FakeResponse:
    def __init__(self, payload, should_fail=False):
        self.payload = payload
        self.should_fail = should_fail

    def raise_for_status(self):
        if self.should_fail:
            raise RuntimeError("boom")

    def json(self):
        return self.payload


class OllamaModelsTests(SimpleTestCase):
    @override_settings(OLLAMA_URL="http://localhost:11434/api/generate")
    def test_lists_models_from_tags_endpoint(self):
        from unittest.mock import patch

        with patch(
            "apps.processing.services.ollama_models.requests.get",
            return_value=FakeResponse({"models": [{"name": "gemma3"}, {"name": "llava"}]}),
        ) as mocked_get:
            models = list_installed_models()

        self.assertEqual(models, ["gemma3", "llava"])
        self.assertEqual(mocked_get.call_args.args[0], "http://localhost:11434/api/tags")

    @override_settings(OLLAMA_URL="http://localhost:11434/api/generate")
    def test_returns_empty_list_when_ollama_is_down(self):
        from unittest.mock import patch

        with patch(
            "apps.processing.services.ollama_models.requests.get",
            side_effect=RuntimeError("down"),
        ):
            models = list_installed_models()

        self.assertEqual(models, [])

    @override_settings(OLLAMA_URL="http://localhost:11434/api/generate")
    def test_returns_normalized_model_snapshot(self):
        from unittest.mock import patch

        payload = {
            "models": [
                {
                    "name": "llama3.2",
                    "size": 123,
                    "modified_at": "2026-04-24T00:00:00Z",
                }
            ]
        }

        with patch(
            "apps.processing.services.ollama_models.requests.get",
            return_value=FakeResponse(payload),
        ):
            snapshot = get_available_models()

        self.assertEqual(snapshot["provider"], "ollama")
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["models"][0]["name"], "llama3.2")
        self.assertEqual(snapshot["models"][0]["label"], "llama3.2")
        self.assertEqual(snapshot["models"][0]["size"], 123)
        self.assertEqual(snapshot["models"][0]["modifiedAt"], "2026-04-24T00:00:00Z")
