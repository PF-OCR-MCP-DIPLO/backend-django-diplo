from django.db import models


class ProcessRun(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Completed with errors"
        FAILED = "failed", "Failed"

    source_docx = models.FileField(upload_to="process_runs/%Y/%m/%d/documents/")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.UPLOADED
    )
    total_images = models.PositiveIntegerField(default=0)
    total_records = models.PositiveIntegerField(default=0)
    excel_file = models.FileField(
        upload_to="process_runs/%Y/%m/%d/exports/", blank=True, null=True
    )
    error_message = models.TextField(blank=True)
    provider_config_snapshot = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SourceImage(models.Model):
    class OCRStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    process_run = models.ForeignKey(
        ProcessRun, related_name="source_images", on_delete=models.CASCADE
    )
    sequence_index = models.PositiveIntegerField()
    image_file = models.FileField(upload_to="process_runs/%Y/%m/%d/images/")
    source_name = models.CharField(max_length=255)
    content_hash = models.CharField(max_length=64, blank=True)
    ocr_status = models.CharField(
        max_length=32, choices=OCRStatus.choices, default=OCRStatus.PENDING
    )
    ocr_raw_text = models.TextField(blank=True)
    ocr_provider = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sequence_index", "id"]
        unique_together = ("process_run", "sequence_index")


class ExtractedDeposit(models.Model):
    process_run = models.ForeignKey(
        ProcessRun, related_name="deposits", on_delete=models.CASCADE
    )
    source_image = models.ForeignKey(
        SourceImage, related_name="deposits", on_delete=models.CASCADE
    )
    sequence_index = models.PositiveIntegerField()
    fecha_consignacion = models.CharField(max_length=10, blank=True)
    hora_consignacion = models.CharField(max_length=5, blank=True)
    referencia = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    is_current_month = models.BooleanField(blank=True, null=True)
    observations = models.JSONField(default=list, blank=True)
    structured_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_index", "id"]


class ProcessingSettings(models.Model):
    class OCRMode(models.TextChoices):
        TESSERACT = "tesseract", "Tesseract"
        VISION = "vision", "Vision"
        AUTO = "auto", "Auto"

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama"
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Gemini"
        DEEPSEEK = "deepseek", "DeepSeek"

    singleton_key = models.CharField(max_length=32, unique=True, default="default")
    ocr_mode = models.CharField(
        max_length=32, choices=OCRMode.choices, default=OCRMode.VISION
    )
    ocr_provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    ocr_model = models.CharField(max_length=128, blank=True)
    llm_provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    llm_model = models.CharField(max_length=128, blank=True)
    request_timeout_seconds = models.PositiveIntegerField(default=320)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ExtractionLog(models.Model):
    process_run = models.ForeignKey(
        ProcessRun, related_name="extraction_logs", on_delete=models.CASCADE
    )
    source_image = models.ForeignKey(
        SourceImage,
        related_name="extraction_logs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    sequence_index = models.PositiveIntegerField(default=0)
    stage = models.CharField(max_length=64)
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=128, blank=True)
    ocr_mode = models.CharField(max_length=32, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    raw_text = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence_index", "id"]
