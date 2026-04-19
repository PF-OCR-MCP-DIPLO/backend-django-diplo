import base64
import io
import zipfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.processing.models import ProcessRun

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

    def test_upload_process_export_and_detail(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/", {"file": upload}, format="multipart"
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
            "/api/documents/upload/", {"file": upload}, format="multipart"
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
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["total_records"], 1)
        self.assertEqual(mocked_ocr.call_count, 1)
        self.assertEqual(payload["source_images"][0]["ocr_status"], "processed")
        self.assertEqual(payload["source_images"][1]["ocr_status"], "failed")
        self.assertTrue(payload["source_images"][1]["error_message"])

    def test_export_requires_completed_job(self):
        upload = SimpleUploadedFile(
            "consignaciones.docx",
            self.docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        upload_response = self.client.post(
            "/api/documents/upload/", {"file": upload}, format="multipart"
        )
        self.assertEqual(upload_response.status_code, 201)
        job_id = upload_response.json()["id"]
        export_response = self.client.post(f"/api/jobs/{job_id}/export/")
        self.assertEqual(export_response.status_code, 409)
