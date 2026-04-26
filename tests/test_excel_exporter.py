from django.core.files.base import ContentFile
from django.test import TestCase
from openpyxl import load_workbook

from apps.processing.models import ExtractedDeposit, ProcessRun, SourceImage
from apps.processing.services.excel_exporter import export_job_to_excel


class ExcelExporterTests(TestCase):
    """Asegura que la exportación preserve orden y datos visibles en Excel."""

    def test_export_keeps_sequence_order(self):
        process_run = ProcessRun.objects.create(
            original_filename="test.docx",
            status=ProcessRun.Status.COMPLETED,
            total_images=2,
        )
        process_run.source_docx.save("test.docx", ContentFile(b"docx"), save=True)
        image_one = SourceImage.objects.create(
            process_run=process_run,
            sequence_index=1,
            source_name="first.png",
            ocr_status=SourceImage.OCRStatus.PROCESSED,
        )
        image_one.image_file.save("first.png", ContentFile(b"png1"), save=True)
        image_two = SourceImage.objects.create(
            process_run=process_run,
            sequence_index=2,
            source_name="second.png",
            ocr_status=SourceImage.OCRStatus.PROCESSED,
        )
        image_two.image_file.save("second.png", ContentFile(b"png2"), save=True)
        ExtractedDeposit.objects.create(
            process_run=process_run,
            source_image=image_one,
            sequence_index=1,
            fecha_consignacion="01/04/2026",
            hora_consignacion="10:00",
            referencia="REF001",
            valor="1000.00",
            is_current_month=True,
            observations=[],
            structured_payload={},
        )
        ExtractedDeposit.objects.create(
            process_run=process_run,
            source_image=image_two,
            sequence_index=2,
            fecha_consignacion="02/04/2026",
            hora_consignacion="11:00",
            referencia="REF002",
            valor="2000.00",
            is_current_month=False,
            observations=["Fecha fuera del mes actual"],
            structured_payload={},
        )
        export_job_to_excel(process_run)
        process_run.refresh_from_db()
        process_run.excel_file.open("rb")
        workbook = load_workbook(process_run.excel_file)
        sheet = workbook.active
        self.assertEqual(sheet["A2"].value, 1)
        self.assertEqual(sheet["D2"].value, "REF001")
        self.assertEqual(sheet["A3"].value, 2)
        self.assertEqual(sheet["D3"].value, "REF002")
        process_run.excel_file.close()
