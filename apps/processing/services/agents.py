from apps.extraction.services.image_validation import validate_source_image
from apps.extraction.services.ocr_service import extract_raw_text
from apps.extraction.services.structuring_service import extract_structured_data
from apps.extraction.services.validators import build_record_observations
from apps.processing.models import ExtractedDeposit, SourceImage


class OCRAgent:
    """Agent responsible for image validation and OCR extraction."""

    def run(self, source_image, runtime_config):
        validate_source_image(source_image)
        return extract_raw_text(source_image, runtime_config)


class StructuringAgent:
    """Agent responsible for turning raw OCR text into structured records."""

    def run(self, source_image, raw_text, runtime_config):
        return extract_structured_data(source_image, raw_text, runtime_config)


class ValidationPersistenceAgent:
    """Agent responsible for validation and persistence of extracted records."""

    def run(self, process_run, source_image, records):
        created_records = 0
        for structured_record in records:
            observations, is_current_month = build_record_observations(
                structured_record.get("fecha_consignacion")
            )

            # If source_image is a mock object (for text processing), create a real SourceImage
            if not hasattr(source_image, "pk") or source_image.pk is None:
                # Create a special SourceImage for text extraction
                source_image = SourceImage.objects.create(
                    process_run=process_run,
                    sequence_index=getattr(source_image, "sequence_index", 0),
                    source_name=getattr(source_image, "source_name", "document_text"),
                    content_hash="",
                    ocr_status=SourceImage.OCRStatus.PROCESSED,
                    ocr_raw_text=getattr(source_image, "ocr_raw_text", ""),
                    ocr_provider=getattr(
                        source_image, "ocr_provider", "text_extraction"
                    ),
                )

            ExtractedDeposit.objects.create(
                process_run=process_run,
                source_image=source_image,
                sequence_index=source_image.sequence_index,
                fecha_consignacion=structured_record.get("fecha_consignacion") or "",
                hora_consignacion=structured_record.get("hora_consignacion") or "",
                referencia=structured_record["referencia"],
                valor=structured_record["valor"],
                is_current_month=is_current_month,
                observations=observations,
                structured_payload=structured_record,
            )
            created_records += 1
        return created_records


class ProcessingSupervisorAgent:
    """Coordinates specialized agents to process one source image."""

    def __init__(self, ocr_agent=None, structuring_agent=None, validation_agent=None):
        self.ocr_agent = ocr_agent or OCRAgent()
        self.structuring_agent = structuring_agent or StructuringAgent()
        self.validation_agent = validation_agent or ValidationPersistenceAgent()

    def process_image(self, process_run, source_image, runtime_config, log_callback):
        ocr_result = self.ocr_agent.run(source_image, runtime_config)
        source_image.ocr_raw_text = ocr_result["text"]
        source_image.ocr_provider = ocr_result["provider"]
        log_callback(
            process_run,
            source_image,
            "ocr_extracted",
            runtime_config,
            provider=ocr_result["provider"],
            model=ocr_result["model"],
            raw_payload=ocr_result["payload"],
            raw_text=ocr_result["text"],
            notes=f"OCR mode resolved to {ocr_result['mode']}",
        )
        structured_result = self.structuring_agent.run(
            source_image,
            ocr_result["text"],
            runtime_config,
        )
        log_callback(
            process_run,
            source_image,
            "llm_structured",
            runtime_config,
            provider=structured_result["provider"],
            model=structured_result["model"],
            raw_payload={"records_count": len(structured_result["records"])},
        )
        records_count = self.validation_agent.run(
            process_run,
            source_image,
            structured_result["records"],
        )
        source_image.ocr_status = SourceImage.OCRStatus.PROCESSED
        source_image.error_message = ""
        source_image.save(
            update_fields=[
                "ocr_status",
                "ocr_raw_text",
                "ocr_provider",
                "error_message",
                "updated_at",
            ]
        )
        return records_count

    def process_text(self, process_run, extracted_text, runtime_config, log_callback):
        """Process extracted text directly without OCR."""
        if not extracted_text.strip():
            return 0

        # Create a mock source_image for logging purposes
        class MockSourceImage:
            def __init__(self):
                self.sequence_index = 0
                self.source_name = "document_text"
                self.ocr_provider = "text_extraction"
                self.ocr_raw_text = extracted_text
                self.pk = None  # This will trigger SourceImage creation in ValidationPersistenceAgent

        mock_source_image = MockSourceImage()

        log_callback(
            process_run,
            mock_source_image,
            "text_extracted",
            runtime_config,
            provider="docx_parser",
            raw_text=extracted_text,
            notes="Text extracted directly from Word document",
        )

        # Use the structuring agent directly with the extracted text
        structured_result = self.structuring_agent.run(
            mock_source_image,
            extracted_text,
            runtime_config,
        )

        log_callback(
            process_run,
            mock_source_image,
            "llm_structured",
            runtime_config,
            provider=structured_result["provider"],
            model=structured_result["model"],
            raw_payload={"records_count": len(structured_result["records"])},
        )

        records_count = self.validation_agent.run(
            process_run,
            mock_source_image,
            structured_result["records"],
        )

        return records_count
