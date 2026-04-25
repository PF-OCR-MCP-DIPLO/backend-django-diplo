from django.test import SimpleTestCase, override_settings

import requests

from apps.api.services.assistant_llm import (
    AssistantProviderError,
    AssistantTextClient,
    TextGenerationConfig,
)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload
        self.raise_for_status_called = False
        self.status_code = 500
        self.text = "boom"

    def raise_for_status(self):
        self.raise_for_status_called = True
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response_payload: dict):
        self.response = FakeResponse(response_payload)
        self.calls = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


class TimeoutSession:
    def post(self, url: str, **kwargs):
        raise requests.Timeout("timeout")


class AssistantTextClientTests(SimpleTestCase):
    @override_settings(OLLAMA_URL="http://ollama.local/api/generate")
    def test_ollama_generate_uses_configured_payload(self):
        session = FakeSession({"response": "respuesta"})
        client = AssistantTextClient(session=session)

        result = client.generate(
            "hola",
            TextGenerationConfig(
                provider="ollama",
                model="gemma",
                timeout=9,
                temperature=0.15,
                num_predict=128,
            ),
        )

        self.assertEqual(result, "respuesta")
        self.assertTrue(session.response.raise_for_status_called)
        self.assertEqual(session.calls[0]["url"], "http://ollama.local/api/generate")
        self.assertEqual(session.calls[0]["timeout"], 9)
        self.assertEqual(session.calls[0]["json"]["model"], "gemma")
        self.assertEqual(session.calls[0]["json"]["prompt"], "hola")
        self.assertEqual(session.calls[0]["json"]["options"]["temperature"], 0.15)
        self.assertEqual(session.calls[0]["json"]["options"]["num_predict"], 128)

    @override_settings(
        ANTHROPIC_URL="https://anthropic.local/messages",
        ANTHROPIC_VERSION="2026-01-01",
    )
    def test_anthropic_generate_reads_content_text(self):
        session = FakeSession({"content": [{"text": "respuesta anthropic"}]})
        client = AssistantTextClient(session=session)

        result = client.generate(
            "hola",
            TextGenerationConfig(
                provider="anthropic",
                model="claude-test",
                timeout=7,
                api_key="test-key",
                temperature=0.1,
            ),
        )

        self.assertEqual(result, "respuesta anthropic")
        call = session.calls[0]
        self.assertEqual(call["url"], "https://anthropic.local/messages")
        self.assertEqual(call["headers"]["x-api-key"], "test-key")
        self.assertEqual(call["headers"]["anthropic-version"], "2026-01-01")
        self.assertEqual(
            call["json"]["messages"], [{"role": "user", "content": "hola"}]
        )

    def test_anthropic_generate_falls_back_to_text_field(self):
        session = FakeSession({"text": "texto plano"})
        client = AssistantTextClient(session=session)

        result = client.generate(
            "hola",
            TextGenerationConfig(
                provider="anthropic",
                model="claude-test",
                timeout=7,
            ),
        )

        self.assertEqual(result, "texto plano")

    @override_settings(OLLAMA_URL="http://ollama.local/api/generate")
    def test_ollama_generate_raises_provider_error_with_detail(self):
        session = FakeSession({"error": "model not found"})

        def _raise_for_status():
            raise requests.HTTPError(response=session.response)

        session.response.raise_for_status = _raise_for_status
        client = AssistantTextClient(session=session)

        with self.assertRaises(AssistantProviderError) as ctx:
            client.generate(
                "hola",
                TextGenerationConfig(
                    provider="ollama",
                    model="gemma4:e2b",
                    timeout=9,
                ),
            )

        self.assertEqual(ctx.exception.provider, "ollama")
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("model not found", ctx.exception.detail)
        self.assertEqual(ctx.exception.code, "provider_unavailable")

    @override_settings(OLLAMA_URL="http://ollama.local/api/generate")
    def test_ollama_generate_maps_memory_error_to_domain_code(self):
        session = FakeSession(
            {
                "error": "model requires more system memory (5.4 GiB) than is available (5.2 GiB)"
            }
        )

        def _raise_for_status():
            raise requests.HTTPError(response=session.response)

        session.response.raise_for_status = _raise_for_status
        client = AssistantTextClient(session=session)

        with self.assertRaises(AssistantProviderError) as ctx:
            client.generate(
                "hola",
                TextGenerationConfig(
                    provider="ollama",
                    model="llama3.2:3b",
                    timeout=9,
                ),
            )

        self.assertEqual(ctx.exception.code, "assistant_model_too_large")
        self.assertIn("qwen3:1.7b", str(ctx.exception))

    @override_settings(OLLAMA_URL="http://ollama.local/api/generate")
    def test_ollama_generate_maps_timeout_to_controlled_error(self):
        client = AssistantTextClient(session=TimeoutSession())

        with self.assertRaises(AssistantProviderError) as ctx:
            client.generate(
                "hola",
                TextGenerationConfig(
                    provider="ollama",
                    model="qwen3:1.7b",
                    timeout=3,
                ),
            )

        self.assertEqual(ctx.exception.code, "provider_timeout")
        self.assertEqual(ctx.exception.provider, "ollama")
