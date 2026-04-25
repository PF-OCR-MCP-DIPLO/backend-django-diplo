from django.test import SimpleTestCase, override_settings

from apps.processing.services.ollama_models import list_installed_models


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
