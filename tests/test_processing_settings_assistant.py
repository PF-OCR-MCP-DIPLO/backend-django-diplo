from django.test import TestCase, override_settings

from apps.api.serializers import ProcessingSettingsSerializer
from apps.processing.models import ProcessingSettings
from apps.processing.services.settings_service import get_or_create_processing_settings


class ProcessingSettingsAssistantTests(TestCase):
    def test_serializer_exposes_assistant_fields_and_validates_model(self):
        settings_obj = get_or_create_processing_settings()
        serializer = ProcessingSettingsSerializer(
            settings_obj,
            data={
                "assistant_provider": "ollama",
                "assistant_model": "gemma3",
                "assistant_temperature": 0.4,
                "assistant_num_predict": 512,
            },
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.assistant_provider, "ollama")
        self.assertEqual(updated.assistant_model, "gemma3")
        self.assertEqual(updated.assistant_temperature, 0.4)
        self.assertEqual(updated.assistant_num_predict, 512)

    def test_serializer_rejects_missing_ollama_assistant_model(self):
        settings_obj = get_or_create_processing_settings()
        serializer = ProcessingSettingsSerializer(
            settings_obj,
            data={"assistant_provider": "ollama", "assistant_model": ""},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("assistant_model", serializer.errors)

    def test_runtime_config_prefers_assistant_model(self):
        settings_obj = get_or_create_processing_settings()
        settings_obj.assistant_provider = "ollama"
        settings_obj.assistant_model = "assistant-test"
        settings_obj.llm_model = "llm-test"
        settings_obj.save()

        from apps.processing.services.settings_service import get_runtime_config

        runtime = get_runtime_config()
        self.assertEqual(runtime.assistant_model, "assistant-test")
        self.assertEqual(runtime.llm_model, "llm-test")
