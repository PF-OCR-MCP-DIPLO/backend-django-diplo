import base64
import io
import zipfile
from unittest.mock import patch

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.processing.models import ProcessRun
from apps.processing.services.settings_service import get_or_create_processing_settings

PNG_ONE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WnR2xQAAAAASUVORK5CYII="
)
PNG_TWO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mNk+M/wHwAEAQH/5N9sLQAAAABJRU5ErkJggg=="
)


def build_docx_with_images(image_map):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rIdImage2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:drawing>
          <a:graphic>
            <a:graphicData>
              <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
                <pic:blipFill>
                  <a:blip r:embed="rIdImage1"/>
                </pic:blipFill>
              </pic:pic>
            </a:graphicData>
          </a:graphic>
        </w:drawing>
      </w:r>
    </w:p>
    <w:p>
      <w:r>
        <w:drawing>
          <a:graphic>
            <a:graphicData>
              <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
                <pic:blipFill>
                  <a:blip r:embed="rIdImage2"/>
                </pic:blipFill>
              </pic:pic>
            </a:graphicData>
          </a:graphic>
        </w:drawing>
      </w:r>
    </w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr("word/media/image1.png", image_map["image1.png"])
        archive.writestr("word/media/image2.png", image_map["image2.png"])
    buffer.seek(0)
    return buffer.getvalue()


def build_docx_without_images():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Documento sin imagenes</w:t></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>""",
        )
    buffer.seek(0)
    return buffer.getvalue()


@override_settings(
    PROCESS_JOBS_ASYNC=False,
    API_KEY="",
    ALLOW_OPEN_API_FOR_DEV=True,
    MCP_ENABLE_MUTATIONS=True,
)
class DocumentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.docx_bytes = build_docx_with_images(
            {"image1.png": PNG_ONE, "image2.png": PNG_TWO}
        )

    def test_health_endpoint(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @override_settings(API_KEY="test-api-key", ALLOW_OPEN_API_FOR_DEV=False)
    def test_sensitive_endpoints_require_api_key(self):
        response = self.client.get("/api/jobs/")
        self.assertEqual(response.status_code, 403)
        authorized = self.client.get("/api/jobs/", HTTP_X_API_KEY="test-api-key")
        self.assertEqual(authorized.status_code, 200)

    def test_upload_rejects_non_docx_with_error_envelope(self):
        upload = SimpleUploadedFile("file.txt", b"nope", content_type="text/plain")
        response = self.client.post(
            "/api/documents/upload/", {"file": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("file", payload["error"]["details"])

    def test_upload_rejects_docx_without_images(self):
        empty_docx = build_docx_without_images()
        upload = SimpleUploadedFile(
            "empty.docx",
            empty_docx,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(
            "/api/documents/upload/", {"file": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "docx_no_images")

    def test_upload_rejects_corrupted_docx(self):
        upload = SimpleUploadedFile(
            "bad.docx",
            b"not-a-zip",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response = self.client.post(
            "/api/documents/upload/", {"file": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_docx")

    def test_job_detail_not_found_uses_error_envelope(self):
        response = self.client.get("/api/jobs/999999/")
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_upload_process_export_and_detail(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        detail = upload_response.json()
        self.assertEqual(detail["total_images"], 2)
        self.assertEqual(
            [item["sequence_index"] for item in detail["source_images"]], [1, 2]
        )
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                side_effect=["OCR 1", "OCR 2"],
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                side_effect=[
                    [
                        {
                            "fecha_consignacion": "01/04/2026",
                            "hora_consignacion": "10:00",
                            "referencia": "REF001",
                            "valor": 150000.0,
                            "archivo_origen": "image1.png",
                        }
                    ],
                    [
                        {
                            "fecha_consignacion": "01/03/2026",
                            "hora_consignacion": "11:00",
                            "referencia": "REF002",
                            "valor": 50000.0,
                            "archivo_origen": "image2.png",
                        }
                    ],
                ],
            ),
        ):
            process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 200)
        processed = process_response.json()
        self.assertEqual(processed["status"], "completed")
        self.assertEqual(processed["total_records"], 2)
        self.assertEqual(processed["source_images"][0]["ocr_status"], "processed")
        self.assertEqual(
            processed["source_images"][1]["deposits"][0]["observations"],
            ["Fecha fuera del mes actual"],
        )
        export_response = self.client.post(f"/api/jobs/{job_id}/export/")
        self.assertEqual(export_response.status_code, 200)
        self.assertTrue(export_response.json()["excel_file"])
        detail_response = self.client.get(f"/api/jobs/{job_id}/")
        self.assertEqual(detail_response.status_code, 200)
        list_response = self.client.get("/api/jobs/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(ProcessRun.objects.get(pk=job_id).deposits.count(), 2)

    def test_process_marks_invalid_images_failed_without_calling_ocr(self):
        invalid_docx = build_docx_with_images(
            {"image1.png": PNG_ONE, "image2.png": b"\x00\x01\x02\x03"}
        )
        upload = SimpleUploadedFile(
            "invalid-image.docx",
            invalid_docx,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                return_value="OCR VALID IMAGE",
            ) as mocked_ocr,
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                return_value=[
                    {
                        "fecha_consignacion": "01/04/2026",
                        "hora_consignacion": "10:00",
                        "referencia": "REF001",
                        "valor": 150000.0,
                        "archivo_origen": "image1.png",
                    }
                ],
            ),
        ):
            process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 200)
        payload = process_response.json()
        self.assertEqual(payload["status"], "completed_with_errors")
        self.assertEqual(payload["total_records"], 1)
        self.assertEqual(mocked_ocr.call_count, 1)
        self.assertEqual(payload["source_images"][0]["ocr_status"], "processed")
        self.assertEqual(payload["source_images"][1]["ocr_status"], "failed")
        self.assertTrue(payload["source_images"][1]["error_message"])

    def test_process_marks_job_failed_when_all_images_fail(self):
        invalid_docx = build_docx_with_images(
            {"image1.png": b"\x00\x01\x02", "image2.png": b"\x03\x04\x05"}
        )
        upload = SimpleUploadedFile(
            "all-invalid.docx",
            invalid_docx,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 200)
        payload = process_response.json()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["total_records"], 0)
        self.assertEqual(payload["source_images"][0]["ocr_status"], "failed")
        self.assertEqual(payload["source_images"][1]["ocr_status"], "failed")
        self.assertTrue(payload["finished_at"])
        refreshed = self.client.get(f"/api/jobs/{job_id}/").json()
        self.assertEqual(refreshed["status"], "failed")

    def test_export_requires_completed_job(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        export_response = self.client.post(f"/api/jobs/{job_id}/export/")
        self.assertEqual(export_response.status_code, 409)
        payload = export_response.json()
        self.assertEqual(payload["error"]["code"], "job_not_exportable")
        self.assertIn("complet", payload["error"]["message"].lower())
        self.assertEqual(payload["error"]["details"]["status"], "uploaded")

    @override_settings(API_KEY="dev")
    def test_sensitive_endpoints_require_api_key_when_configured(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]

        # Missing key
        process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 403)
        self.assertEqual(process_response.json()["error"]["code"], "forbidden")

        export_response = self.client.post(f"/api/jobs/{job_id}/export/")
        self.assertEqual(export_response.status_code, 403)
        self.assertEqual(export_response.json()["error"]["code"], "forbidden")

        # With key
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                side_effect=["OCR 1", "OCR 2"],
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                return_value=[],
            ),
        ):
            process_ok = self.client.post(
                f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
            )
        self.assertEqual(process_ok.status_code, 200)

    def test_settings_endpoints(self):
        response = self.client.get("/api/processing/settings/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ocr_mode"], "vision")
        self.assertFalse(payload["has_ocr_api_key"])
        self.assertFalse(payload["has_llm_api_key"])
        patch_response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "auto",
                "ocr_provider": "ollama",
                "ocr_model": "gemma4:e2b",
                "llm_provider": "ollama",
                "llm_model": "gemma3:1b-it-qat",
                "request_timeout_seconds": 120,
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        options_response = self.client.get("/api/processing/settings/options/")
        self.assertEqual(options_response.status_code, 200)
        self.assertIn("auto", options_response.json()["ocr_modes"])

    def test_settings_options_returns_complete_defensive_contract(self):
        with patch(
            "apps.processing.services.settings_service.list_installed_models",
            side_effect=RuntimeError("ollama unavailable"),
        ):
            response = self.client.get("/api/processing/settings/options/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ocr_modes"], ["tesseract", "vision", "auto"])
        self.assertEqual(
            payload["providers"]["ocr"], ["ollama", "openai", "gemini", "deepseek"]
        )
        self.assertEqual(
            payload["providers"]["llm"],
            ["ollama", "openai", "gemini", "deepseek", "anthropic"],
        )
        self.assertIn("provider_models", payload)
        self.assertIn("provider_requirements", payload)
        for provider in payload["providers"]["llm"]:
            self.assertIn(provider, payload["provider_models"])
            self.assertIn(provider, payload["provider_requirements"])
            self.assertIsInstance(payload["provider_models"][provider]["ocr"], list)
            self.assertIsInstance(payload["provider_models"][provider]["llm"], list)
            self.assertIn("operational", payload["provider_requirements"][provider])
            self.assertIn(
                "requires_api_key", payload["provider_requirements"][provider]
            )

    def test_settings_rejects_invalid_payload_with_clear_error(self):
        response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "vision",
                "ocr_provider": "anthropic",
                "llm_provider": "ollama",
                "llm_model": "gemma3:1b-it-qat",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("ocr_provider", payload["error"]["details"])

    def test_job_contract_is_safe_without_images_or_export(self):
        process_run = ProcessRun.objects.create(
            original_filename="empty.docx", status=ProcessRun.Status.UPLOADED
        )

        detail_response = self.client.get(f"/api/jobs/{process_run.pk}/")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["source_images"], [])
        self.assertIsNone(detail["excel_file"])
        self.assertIn("provider_config_snapshot", detail)

        list_response = self.client.get("/api/jobs/")
        self.assertEqual(list_response.status_code, 200)
        self.assertIsInstance(list_response.json(), list)

    def test_job_logs_not_found_uses_error_envelope(self):
        response = self.client.get("/api/jobs/999999/logs/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_export_missing_job_uses_error_envelope(self):
        response = self.client.post("/api/jobs/999999/export/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_settings_validation_for_non_operational_providers(self):
        response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "vision",
                "ocr_provider": "openai",
                "llm_provider": "deepseek",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        details = payload["error"]["details"]
        self.assertIn("ocr_provider", details)
        self.assertIn("ocr_api_key", details)
        self.assertIn("llm_provider", details)
        self.assertIn("llm_api_key", details)

    def test_settings_validation_requires_models_and_timeout_range(self):
        response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "vision",
                "ocr_provider": "ollama",
                "ocr_model": "",
                "llm_provider": "ollama",
                "llm_model": "",
                "request_timeout_seconds": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        details = payload["error"]["details"]
        self.assertIn("ocr_model", details)
        self.assertIn("llm_model", details)
        self.assertIn("request_timeout_seconds", details)

    def test_settings_tesseract_normalizes_provider(self):
        response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "tesseract",
                "ocr_provider": "openai",
                "ocr_model": "spa",
                "llm_provider": "ollama",
                "llm_model": "gemma3:1b-it-qat",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ocr_provider"], "ollama")

    def test_tesseract_mode_processing_does_not_send_timeout_to_ocr(self):
        settings_response = self.client.patch(
            "/api/processing/settings/",
            {
                "ocr_mode": "tesseract",
                "ocr_model": "spa",
                "llm_provider": "ollama",
                "llm_model": "gemma3:1b-it-qat",
                "request_timeout_seconds": 45,
            },
            format="json",
        )
        self.assertEqual(settings_response.status_code, 200)
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        with (
            patch(
                "apps.extraction.providers.ocr.tesseract.TesseractOCRProvider.extract_text",
                side_effect=["OCR TESS 1", "OCR TESS 2"],
            ) as mocked_ocr,
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                return_value=[],
            ),
        ):
            process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 200)
        first_call_kwargs = mocked_ocr.call_args_list[0].kwargs
        self.assertNotIn("timeout_seconds", first_call_kwargs)

    def test_job_logs_endpoint(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                side_effect=["OCR 1", "OCR 2"],
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                side_effect=[
                    [
                        {
                            "fecha_consignacion": "01/04/2026",
                            "hora_consignacion": "10:00",
                            "referencia": "REF001",
                            "valor": 150000.0,
                            "archivo_origen": "image1.png",
                        }
                    ],
                    [],
                ],
            ),
        ):
            process_response = self.client.post(f"/api/jobs/{job_id}/process/")
        self.assertEqual(process_response.status_code, 200)
        logs_response = self.client.get(f"/api/jobs/{job_id}/logs/")
        self.assertEqual(logs_response.status_code, 200)
        self.assertGreaterEqual(len(logs_response.json()), 3)

    @override_settings(API_KEY="dev")
    def test_bulk_deposit_corrections_persist_and_refresh_detail(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        job_id = upload_response.json()["id"]

        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                side_effect=["OCR 1", "OCR 2"],
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                side_effect=[
                    [
                        {
                            "fecha_consignacion": "01/04/2026",
                            "hora_consignacion": "10:00",
                            "referencia": "REF001",
                            "valor": 150000.0,
                            "archivo_origen": "image1.png",
                        }
                    ],
                    [],
                ],
            ),
        ):
            process_response = self.client.post(
                f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
            )

        self.assertEqual(process_response.status_code, 200)
        deposit_id = process_response.json()["source_images"][0]["deposits"][0]["id"]
        correction_response = self.client.patch(
            f"/api/jobs/{job_id}/deposits/",
            {
                "items": [
                    {
                        "id": deposit_id,
                        "fecha_consignacion": "22/04/2026",
                        "hora_consignacion": "15:45",
                        "referencia": "REF999",
                        "valor": "175000",
                    }
                ]
            },
            format="json",
            HTTP_X_API_KEY="dev",
        )

        self.assertEqual(correction_response.status_code, 200)
        corrected = correction_response.json()["source_images"][0]["deposits"][0]
        self.assertEqual(corrected["fecha_consignacion"], "22/04/2026")
        self.assertEqual(corrected["hora_consignacion"], "15:45")
        self.assertEqual(corrected["referencia"], "REF999")
        self.assertEqual(corrected["valor"], "175000.00")
        self.assertEqual(corrected["observations"], [])

        detail_response = self.client.get(f"/api/jobs/{job_id}/", HTTP_X_API_KEY="dev")
        refreshed = detail_response.json()["source_images"][0]["deposits"][0]
        self.assertEqual(refreshed["referencia"], "REF999")

    @override_settings(API_KEY="dev")
    def test_bulk_deposit_corrections_require_api_key(self):
        process_run = ProcessRun.objects.create(
            original_filename="test.docx", status=ProcessRun.Status.COMPLETED
        )
        response = self.client.patch(
            f"/api/jobs/{process_run.pk}/deposits/",
            {
                "items": [
                    {
                        "id": 1,
                        "fecha_consignacion": "22/04/2026",
                        "hora_consignacion": "15:45",
                        "referencia": "REF999",
                        "valor": "175000",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(API_KEY="dev")
    def test_reprocess_deposit_endpoint_reprocesses_single_image(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        job_id = upload_response.json()["id"]
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                side_effect=["OCR 1", "OCR 2"],
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                side_effect=[
                    [
                        {
                            "fecha_consignacion": "01/04/2026",
                            "hora_consignacion": "10:00",
                            "referencia": "REF001",
                            "valor": 150000.0,
                            "archivo_origen": "image1.png",
                        }
                    ],
                    [],
                ],
            ),
        ):
            process_response = self.client.post(
                f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
            )
        deposit_id = process_response.json()["source_images"][0]["deposits"][0]["id"]
        with (
            patch(
                "apps.extraction.providers.ocr.ollama_vision.OllamaVisionOCRProvider.extract_text",
                return_value="OCR 1 REPROCESS",
            ),
            patch(
                "apps.extraction.providers.llm.ollama_text.OllamaTextLLMProvider.extract",
                return_value=[
                    {
                        "fecha_consignacion": "02/04/2026",
                        "hora_consignacion": "11:00",
                        "referencia": "REF777",
                        "valor": 170000.0,
                        "archivo_origen": "image1.png",
                    }
                ],
            ),
        ):
            response = self.client.post(
                f"/api/jobs/{job_id}/deposits/{deposit_id}/reprocess/",
                HTTP_X_API_KEY="dev",
            )
        self.assertEqual(response.status_code, 200)
        refreshed = response.json()["source_images"][0]["deposits"][0]
        self.assertEqual(refreshed["referencia"], "REF777")

    @override_settings(PROCESS_JOBS_ASYNC=True, API_KEY="dev")
    def test_process_endpoint_returns_accepted_when_async_enabled(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
            HTTP_X_API_KEY="dev",
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]

        def fake_start(job):
            ProcessRun.objects.filter(pk=job.pk).update(
                status=ProcessRun.Status.PROCESSING
            )
            return ProcessRun.objects.get(pk=job.pk)

        with patch(
            "apps.api.views.start_job_processing",
            side_effect=fake_start,
        ):
            response = self.client.post(
                f"/api/jobs/{job_id}/process/", HTTP_X_API_KEY="dev"
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "processing")


class AssistantChatApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_chat_endpoint_accepts_frontend_contract(self):
        with patch(
            "apps.api.services.assistant_chat.AssistantAgent"
        ) as mocked_agent_class:
            mocked_agent = mocked_agent_class.return_value
            mocked_agent.answer.return_value = {
                "reply": "Consulta lista.",
                "tool": "query_database",
                "data": {"rows": []},
            }

            response = self.client.post(
                "/api/assistant/chat/",
                {
                    "messages": [{"role": "user", "content": "Dame el resumen"}],
                    "job_id": 12,
                    "errors": 2,
                    "query_context": {"scope": "results"},
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["reply"], "Consulta lista.")
        self.assertEqual(payload["message"], "Consulta lista.")
        self.assertEqual(payload["tool"], "query_database")
        self.assertEqual(payload["data"], {"rows": []})
        self.assertEqual(payload["query_context"], {"scope": "results"})
        self.assertFalse(payload["show_debug_details"])
        mocked_agent.answer.assert_called_once_with(
            messages=[{"role": "user", "content": "Dame el resumen"}],
            job_id=12,
            errors=2,
            query_context={"scope": "results"},
        )

    def test_chat_endpoint_accepts_job_id_camel_alias(self):
        with patch(
            "apps.api.services.assistant_chat.AssistantAgent"
        ) as mocked_agent_class:
            mocked_agent = mocked_agent_class.return_value
            mocked_agent.answer.return_value = {
                "reply": "Estado consultado.",
                "tool": "get_job_status",
                "data": {"id": 7},
            }

            response = self.client.post(
                "/api/assistant/chat/",
                {
                    "messages": [{"role": "user", "content": "Estado del job"}],
                    "jobId": 7,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["query_context"], {})
        mocked_agent.answer.assert_called_once_with(
            messages=[{"role": "user", "content": "Estado del job"}],
            job_id=7,
            errors=0,
            query_context={},
        )

    def test_chat_endpoint_rejects_invalid_payload(self):
        response = self.client.post(
            "/api/assistant/chat/",
            {"messages": [{"role": "client", "content": "Hola"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("messages", payload["error"]["details"])

    def test_chat_endpoint_rejects_conflicting_job_ids(self):
        response = self.client.post(
            "/api/assistant/chat/",
            {
                "messages": [{"role": "user", "content": "Hola"}],
                "job_id": 1,
                "jobId": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertIn("job_id", payload["error"]["details"])

    def test_chat_endpoint_returns_controlled_unavailable_response(self):
        with patch(
            "apps.api.services.assistant_chat.AssistantAgent"
        ) as mocked_agent_class:
            mocked_agent = mocked_agent_class.return_value
            mocked_agent.answer.return_value = {
                "reply": "El asistente no esta disponible temporalmente.",
                "tool": "none",
                "data": {"detail": "assistant_unavailable"},
            }

            response = self.client.post(
                "/api/assistant/chat/",
                {"messages": [{"role": "user", "content": "Hola"}]},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tool"], "none")
        self.assertEqual(payload["data"]["detail"], "assistant_unavailable")
        self.assertEqual(
            payload["message"], "El asistente no esta disponible temporalmente."
        )
        self.assertEqual(payload["query_context"], {})

    def test_chat_endpoint_handles_missing_job_without_stack_trace(self):
        response = self.client.post(
            "/api/assistant/chat/",
            {
                "messages": [{"role": "user", "content": "estado del job"}],
                "job_id": 999999,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tool"], "none")
        self.assertEqual(payload["data"]["detail"], "assistant_unavailable")
        self.assertEqual(
            payload["message"],
            "El asistente no esta disponible temporalmente. Verifica la configuracion del proveedor LLM e intenta de nuevo.",
        )
        self.assertNotIn("Traceback", payload["reply"])
        self.assertNotIn("Traceback", str(payload["data"]))

    def test_chat_endpoint_hides_technical_provider_errors_when_debug_is_disabled(self):
        with patch(
            "apps.api.services.assistant_chat.AssistantAgent"
        ) as mocked_agent_class:
            mocked_agent = mocked_agent_class.return_value
            mocked_agent.answer.return_value = {
                "reply": "No disponible",
                "tool": "none",
                "data": {
                    "detail": "assistant_provider_error",
                    "error": "stack interno",
                },
                "debug": {"errors": ["stack interno"]},
            }

            response = self.client.post(
                "/api/assistant/chat/",
                {"messages": [{"role": "user", "content": "Hola"}]},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["detail"], "assistant_provider_error")
        self.assertNotIn("error", payload["data"])
        self.assertEqual(payload["debug"]["errors"], [])

    def test_chat_endpoint_keeps_technical_provider_errors_when_debug_is_enabled(self):
        settings_obj = get_or_create_processing_settings()
        settings_obj.assistant_show_debug_details = True
        settings_obj.save(update_fields=["assistant_show_debug_details"])

        with patch(
            "apps.api.services.assistant_chat.AssistantAgent"
        ) as mocked_agent_class:
            mocked_agent = mocked_agent_class.return_value
            mocked_agent.answer.return_value = {
                "reply": "No disponible",
                "tool": "none",
                "data": {
                    "detail": "assistant_provider_error",
                    "error": "stack interno",
                },
                "debug": {"errors": ["stack interno"]},
            }

            response = self.client.post(
                "/api/assistant/chat/",
                {"messages": [{"role": "user", "content": "Hola"}]},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["error"], "stack interno")
        self.assertEqual(payload["debug"]["errors"], ["stack interno"])

    def test_chat_endpoint_cors_allows_frontend_api_key_header(self):
        response = self.client.options(
            "/api/assistant/chat/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-api-key",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )
        allowed_headers = response.headers["access-control-allow-headers"]
        self.assertIn("content-type", allowed_headers)
        self.assertIn("x-api-key", allowed_headers)

    def test_ollama_models_endpoint_returns_snapshot(self):
        with patch("apps.processing.services.ollama_models.requests.get") as mocked_get:
            mocked_get.return_value.raise_for_status.return_value = None
            mocked_get.return_value.json.return_value = {
                "models": [
                    {
                        "name": "llama3.2",
                        "size": 123,
                        "modified_at": "2026-04-24T00:00:00Z",
                    }
                ]
            }

            response = self.client.get("/api/processing/ollama/models/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "ollama")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["models"][0]["name"], "llama3.2")
