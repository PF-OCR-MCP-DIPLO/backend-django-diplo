from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase

from apps.extraction.services.ocr_service import score_ocr_text
from apps.processing.models import ExtractionLog, ProcessRun, SourceImage
from apps.processing.services.orchestrator import process_prepared_job
from apps.processing.services.settings_service import RuntimeProcessingConfig

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xc4\x15\x1b"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class OcrPipelineStabilityTests(SimpleTestCase):
    def test_score_ocr_text_detects_bank_fields(self):
        self.assertEqual(score_ocr_text(""), 0)
        self.assertLess(
            score_ocr_text("abc"),
            score_ocr_text(
                "10/04/2026 08:30 ref 12345 consignacion banco valor $10.000"
            ),
        )
        self.assertGreater(
            score_ocr_text(
                "10/04/2026 08:30 ref 12345 consignacion banco valor $10.000"
            ),
            10,
        )


def _runtime_config(ocr_mode="vision"):
    return RuntimeProcessingConfig(
        ocr_mode=ocr_mode,
        ocr_provider="ollama",
        ocr_model="spa",
        vision_model="gemma4:e2b",
        llm_provider="ollama",
        llm_model="gemma3:1b-it-qat",
        assistant_provider="ollama",
        assistant_model="qwen2.5:7b",
        assistant_api_key="",
        assistant_temperature=0.0,
        assistant_num_predict=512,
        assistant_show_debug_details=False,
        ocr_api_key="",
        llm_api_key="",
        request_timeout_seconds=30,
        valid_consignation_month=4,
        valid_consignation_year=2026,
        extraction_criteria={"fields": []},
    )


def _create_job_with_images(count):
    job = ProcessRun.objects.create(
        original_filename="stability.docx",
        status=ProcessRun.Status.PROCESSING,
    )
    for index in range(1, count + 1):
        SourceImage.objects.create(
            process_run=job,
            sequence_index=index,
            source_name=f"image{index}.png",
            image_file=ContentFile(PNG_BYTES, name=f"image{index}.png"),
        )
    return job


def _ocr_result(text, provider="ollama", mode="vision"):
    return {
        "text": text,
        "provider": provider,
        "model": "gemma4:e2b",
        "mode": mode,
        "payload": {
            "score": score_ocr_text(text),
            "ocr_raw_text_chars": len(text),
            "ocr_raw_text_sample": text[:500],
        },
    }


def _record(index, referencia=None, valor=50000.0):
    payload = {
        "fecha_consignacion": "15/04/2026",
        "hora_consignacion": "09:30",
        "referencia": referencia or f"REF{index:03d}",
        "valor": valor,
        "archivo_origen": f"image{index}.png",
    }
    return payload


class OcrPipelineDiagnosticsRegressionTests(TestCase):
    def test_tesseract_five_images_incomplete_record_is_not_silent(self):
        job = _create_job_with_images(5)
        config = _runtime_config("tesseract")
        ocr_results = [
            _ocr_result(
                f"Banco consignacion referencia REF{index:03d} valor $50.000 fecha 15/04/2026",
                provider="tesseract",
                mode="tesseract",
            )
            for index in range(1, 6)
        ]
        structured_results = [[_record(index)] for index in range(1, 5)] + [
            [{"fecha_consignacion": "15/04/2026", "referencia": "REF005"}]
        ]

        with (
            patch("apps.processing.services.agents.validate_source_image"),
            patch(
                "apps.processing.services.agents.extract_raw_text",
                side_effect=ocr_results,
            ),
            patch(
                "apps.processing.services.agents.extract_structured_data",
                side_effect=[
                    {
                        "records": records,
                        "provider": "ollama",
                        "model": "gemma",
                        "payload": {"structured_records_count": len(records)},
                    }
                    for records in structured_results
                ],
            ),
        ):
            processed = process_prepared_job(job, config)

        self.assertEqual(processed.status, ProcessRun.Status.COMPLETED_WITH_ERRORS)
        self.assertEqual(processed.deposits.count(), 4)
        self.assertTrue(
            ExtractionLog.objects.filter(
                process_run=job, stage="record_skipped"
            ).exists()
        )
        self.assertTrue(
            ExtractionLog.objects.filter(
                process_run=job, stage="persistence_mismatch"
            ).exists()
        )

    def test_ocr_text_with_zero_structured_records_is_not_clean_success(self):
        job = _create_job_with_images(1)
        config = _runtime_config("tesseract")

        with (
            patch("apps.processing.services.agents.validate_source_image"),
            patch(
                "apps.processing.services.agents.extract_raw_text",
                return_value=_ocr_result(
                    "Banco consignacion referencia REFEMPTY comprobante aprobado sin valor visible",
                    provider="tesseract",
                    mode="tesseract",
                ),
            ),
            patch(
                "apps.processing.services.agents.extract_structured_data",
                return_value={
                    "records": [],
                    "provider": "ollama",
                    "model": "gemma",
                    "payload": {"structured_records_count": 0},
                },
            ),
        ):
            processed = process_prepared_job(job, config)

        self.assertEqual(processed.status, ProcessRun.Status.FAILED)
        self.assertEqual(processed.total_records, 0)
        self.assertTrue(
            ExtractionLog.objects.filter(
                process_run=job, stage="structuring_empty"
            ).exists()
        )
        self.assertFalse(
            ExtractionLog.objects.filter(
                process_run=job,
                stage="validation_passed",
                raw_payload__records_validated=0,
            ).exists()
        )

    def test_auto_prefers_ocr_candidate_with_more_structured_valid_records(self):
        job = _create_job_with_images(1)
        config = _runtime_config("auto")
        tesseract_text = "\n".join(
            f"Banco ref TES{index:03d} valor $50.000 fecha 15/04/2026"
            for index in range(1, 6)
        )
        vision_text = "\n".join(
            f"Banco comprobante vision ref VIS{index:03d} valor $50.000 fecha 15/04/2026 aprobado"
            for index in range(1, 5)
        )

        def structure_by_text(_source_image, text, _runtime_config):
            if "TES005" in text:
                records = [
                    _record(index, referencia=f"TES{index:03d}")
                    for index in range(1, 6)
                ]
            else:
                records = [
                    _record(index, referencia=f"VIS{index:03d}")
                    for index in range(1, 5)
                ]
            return {
                "records": records,
                "provider": "ollama",
                "model": "gemma",
                "payload": {"structured_records_count": len(records)},
            }

        with (
            patch("apps.processing.services.agents.validate_source_image"),
            patch(
                "apps.extraction.services.ocr_service._run_tesseract",
                return_value=_ocr_result(
                    tesseract_text,
                    provider="tesseract",
                    mode="tesseract",
                ),
            ),
            patch(
                "apps.extraction.services.ocr_service._run_vision",
                return_value=_ocr_result(vision_text, provider="ollama", mode="vision"),
            ),
            patch(
                "apps.processing.services.agents.extract_structured_data",
                side_effect=structure_by_text,
            ),
        ):
            processed = process_prepared_job(job, config)

        self.assertEqual(processed.status, ProcessRun.Status.COMPLETED)
        self.assertEqual(processed.total_records, 5)
        self.assertEqual(
            set(processed.deposits.values_list("referencia", flat=True)),
            {f"TES{index:03d}" for index in range(1, 6)},
        )
        selected = ExtractionLog.objects.get(process_run=job, stage="auto_ocr_selected")
        self.assertEqual(selected.raw_payload["selected_engine"], "tesseract")
        self.assertEqual(selected.raw_payload["selected_structured_records_count"], 5)

    def test_persistence_mismatch_is_logged_when_no_structured_records_persist(self):
        job = _create_job_with_images(1)
        config = _runtime_config("vision")

        with (
            patch("apps.processing.services.agents.validate_source_image"),
            patch(
                "apps.processing.services.agents.extract_raw_text",
                return_value=_ocr_result(
                    "Banco consignacion referencia REFMISS valor $50.000 fecha 15/04/2026"
                ),
            ),
            patch(
                "apps.processing.services.agents.extract_structured_data",
                return_value={
                    "records": [{"fecha_consignacion": "15/04/2026", "valor": ""}],
                    "provider": "ollama",
                    "model": "gemma",
                    "payload": {"structured_records_count": 1},
                },
            ),
        ):
            processed = process_prepared_job(job, config)

        self.assertEqual(processed.status, ProcessRun.Status.FAILED)
        mismatch = ExtractionLog.objects.get(
            process_run=job,
            stage="persistence_mismatch",
        )
        self.assertEqual(mismatch.raw_payload["structured_records_count"], 1)
        self.assertEqual(mismatch.raw_payload["persisted_records_count"], 0)

    def test_normal_five_images_five_deposits_regression(self):
        job = _create_job_with_images(5)
        config = _runtime_config("tesseract")

        with (
            patch("apps.processing.services.agents.validate_source_image"),
            patch(
                "apps.processing.services.agents.extract_raw_text",
                side_effect=[
                    _ocr_result(
                        f"Banco consignacion referencia REF{index:03d} valor $50.000 fecha 15/04/2026",
                        provider="tesseract",
                        mode="tesseract",
                    )
                    for index in range(1, 6)
                ],
            ),
            patch(
                "apps.processing.services.agents.extract_structured_data",
                side_effect=[
                    {
                        "records": [_record(index)],
                        "provider": "ollama",
                        "model": "gemma",
                        "payload": {"structured_records_count": 1},
                    }
                    for index in range(1, 6)
                ],
            ),
        ):
            processed = process_prepared_job(job, config)

        self.assertEqual(processed.status, ProcessRun.Status.COMPLETED)
        self.assertEqual(processed.total_records, 5)
        self.assertEqual(processed.deposits.count(), 5)
