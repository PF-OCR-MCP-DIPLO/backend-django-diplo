import os
import subprocess
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.processing.models import ExtractionLog, ProcessingSettings, ProcessRun
from apps.processing.services.diagnostics import (
    stage_timer,
    summarize_job_diagnostics,
    summarize_processing_state,
    summarize_provider_health,
)
from apps.processing.services.settings_service import get_or_create_processing_settings
from apps.extraction.services.structuring_service import extract_structured_data
from tests.test_api import build_docx_with_images, PNG_ONE, PNG_TWO


@override_settings(
    PROCESS_JOBS_ASYNC=False,
    API_KEY="",
    ALLOW_OPEN_API_FOR_DEV=True,
    STUB_PROVIDERS=True,
)
class ProcessingDiagnosticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.docx_bytes = build_docx_with_images(
            {"image1.png": PNG_ONE, "image2.png": PNG_TWO}
        )

    def _upload_job(self):
        upload = SimpleUploadedFile(
            "diagnostics.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def test_diagnostics_endpoint_returns_stage_summary(self):
        job_id = self._upload_job()
        response = self.client.post(
            f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
        )
        self.assertEqual(response.status_code, 200)

        diagnostics = self.client.get(
            f"/api/jobs/{job_id}/diagnostics/", HTTP_X_API_KEY="dev"
        )

        self.assertEqual(diagnostics.status_code, 200)
        summary = diagnostics.json()["summary"]
        self.assertEqual(summary["ocr_calls"], 2)
        self.assertEqual(summary["llm_calls"], 2)
        self.assertIsNotNone(summary["slowest_stage"])

    def test_stage_timer_records_duration_when_exception_is_raised(self):
        job = ProcessRun.objects.create(
            original_filename="timer.docx",
            status=ProcessRun.Status.PROCESSING,
        )

        with self.assertRaises(RuntimeError):
            with stage_timer(process_run=job, stage="ocr"):
                raise RuntimeError("provider exploded")

        event = ExtractionLog.objects.get(process_run=job, stage="ocr", is_error=True)
        self.assertEqual(event.raw_payload["status"], "failed")
        self.assertIn("duration_ms", event.raw_payload)
        self.assertEqual(event.raw_payload["error_class"], "RuntimeError")

    def test_process_with_stub_generates_expected_diagnostic_events(self):
        job_id = self._upload_job()
        response = self.client.post(
            f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
        )

        self.assertEqual(response.status_code, 200)
        job = ProcessRun.objects.get(pk=job_id)
        summary = summarize_job_diagnostics(job)["summary"]
        self.assertEqual(summary["ocr_calls"], 2)
        self.assertEqual(summary["llm_calls"], 2)
        self.assertEqual(
            job.extraction_logs.filter(stage="image_validation").count(), 4
        )

    def test_provider_health_detects_missing_installed_model(self):
        settings_obj = get_or_create_processing_settings()
        settings_obj.ocr_mode = ProcessingSettings.OCRMode.VISION
        settings_obj.ocr_model = "missing-vision"
        settings_obj.llm_model = "missing-llm"
        settings_obj.save()

        with patch(
            "apps.processing.services.diagnostics.get_available_models",
            return_value={
                "available": True,
                "models": [{"name": "present", "size": 1}],
                "error": None,
            },
        ):
            health = summarize_provider_health()

        self.assertFalse(health["checks"]["ocr_model_exists"])
        self.assertFalse(health["checks"]["llm_model_exists"])
        self.assertGreaterEqual(len(health["warnings"]), 2)

    def test_timeout_event_is_marked_timeout(self):
        job = ProcessRun.objects.create(
            original_filename="timeout.docx",
            status=ProcessRun.Status.PROCESSING,
        )

        with self.assertRaises(TimeoutError):
            with stage_timer(process_run=job, stage="llm_structuring"):
                raise TimeoutError("provider timed out")

        event = ExtractionLog.objects.get(
            process_run=job,
            stage="llm_structuring",
            is_error=True,
        )
        self.assertEqual(event.raw_payload["status"], "timeout")

    @override_settings(STUB_PROVIDERS=False, LLM_MAX_RETRIES=1, LLM_RETRY_DELAY=0)
    def test_llm_provider_timeout_raises_for_pipeline_diagnostics(self):
        runtime_config = SimpleNamespace(
            llm_provider="ollama",
            llm_model="gemma3:1b-it-qat",
            request_timeout_seconds=1,
            extraction_criteria={},
        )
        source_image = SimpleNamespace(source_name="image.png")

        with patch(
            "apps.extraction.providers.llm.ollama_text.requests.post",
            side_effect=requests.exceptions.Timeout("slow"),
        ):
            with self.assertRaises(TimeoutError):
                extract_structured_data(source_image, "OCR text", runtime_config)

    def test_processing_state_marks_stale_processing(self):
        job = ProcessRun.objects.create(
            original_filename="stale.docx",
            status=ProcessRun.Status.PROCESSING,
            started_at=timezone.now() - timedelta(minutes=20),
        )
        log = ExtractionLog.objects.create(
            process_run=job,
            stage="job_started",
        )
        ExtractionLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )

        state = summarize_processing_state(job)

        self.assertTrue(state["stale_processing"])

    def test_debug_script_runs_in_stub_mode(self):
        report_path = "/tmp/processing-diagnostics-test-report.json"
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/debug_processing_pipeline.py",
                "--stub",
                "--sync",
                "--max-images",
                "1",
                "--report-json",
                report_path,
            ],
            cwd=os.getcwd(),
            env={**os.environ, "STUB_PROVIDERS": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertTrue(os.path.exists(report_path))
