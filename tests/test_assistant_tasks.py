from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase

from apps.api.services.assistant_tasks import (
    AssistantTask,
    build_assistant_task_context,
    resolve_assistant_task,
)
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    SourceImage,
)


class AssistantTaskTests(TestCase):
    def setUp(self):
        self.process_run = ProcessRun.objects.create(
            source_docx=ContentFile(b"docx", name="job.docx"),
            original_filename="job.docx",
            status=ProcessRun.Status.COMPLETED_WITH_ERRORS,
            total_images=1,
            total_records=1,
        )
        self.source_image = SourceImage.objects.create(
            process_run=self.process_run,
            sequence_index=1,
            image_file=ContentFile(b"img", name="image.png"),
            source_name="image.png",
        )
        self.deposit = ExtractedDeposit.objects.create(
            process_run=self.process_run,
            source_image=self.source_image,
            sequence_index=1,
            referencia="REF001",
            valor=Decimal("120000.00"),
            fecha_consignacion="2026-04-22",
            hora_consignacion="10:00",
            observations=["Fecha fuera del mes actual"],
        )
        ExtractionLog.objects.create(
            process_run=self.process_run,
            source_image=self.source_image,
            sequence_index=1,
            stage="ocr",
            provider="ollama",
            model="llama3.2",
            notes="OCR ok",
        )

    def test_resolves_task_from_user_intent_and_context(self):
        task = resolve_assistant_task(
            user_message="resume este job",
            job_id=self.process_run.id,
            query_context={},
            tool="get_job_status",
        )
        self.assertEqual(task.name, "explain_job_summary")

        row_task = resolve_assistant_task(
            user_message="explica esta fila",
            job_id=self.process_run.id,
            query_context={"resultId": self.deposit.id},
            tool="none",
        )
        self.assertEqual(row_task.name, "explain_row_issue")

    def test_builds_concise_context_for_selected_row_and_logs(self):
        task = AssistantTask(
            name="summarize_extraction_logs",
            summary="Resumir logs del job",
        )
        context = build_assistant_task_context(
            task=task,
            job_id=self.process_run.id,
            query_context={"resultId": self.deposit.id},
        )

        self.assertEqual(context["job"]["id"], self.process_run.id)
        self.assertEqual(context["findings"]["rows_with_observations"], 1)
        self.assertEqual(context["selected_row"]["referencia"], "REF001")
        self.assertEqual(context["logs"][0]["stage"], "ocr")

    def test_builds_context_when_job_is_missing(self):
        task = AssistantTask(
            name="answer_general_question",
            summary="Responder conversación general",
        )
        context = build_assistant_task_context(
            task=task,
            job_id=999999,
            query_context={},
        )

        self.assertFalse(context["job_found"])
