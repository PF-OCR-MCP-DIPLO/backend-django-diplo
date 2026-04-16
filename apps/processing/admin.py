from django.contrib import admin

from apps.processing.models import ExtractedDeposit, ProcessRun, SourceImage


@admin.register(ProcessRun)
class ProcessRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "status",
        "total_images",
        "total_records",
    )


@admin.register(SourceImage)
class SourceImageAdmin(admin.ModelAdmin):
    list_display = ("id", "process_run", "sequence_index", "source_name", "ocr_status")


@admin.register(ExtractedDeposit)
class ExtractedDepositAdmin(admin.ModelAdmin):
    list_display = ("id", "process_run", "sequence_index", "referencia", "valor")
