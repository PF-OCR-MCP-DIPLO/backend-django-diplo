"""Modelos de persistencia para ejecuciones, fuentes, depósitos y ajustes.

El esquema refleja el ciclo upload -> OCR/LLM -> corrección -> exportación y
guarda trazabilidad suficiente para auditoría y reproceso parcial.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_valid_consignation_month():
    """Mes inicial sugerido al crear settings; no es regla de negocio."""
    return timezone.localdate().month


def default_valid_consignation_year():
    """Año inicial sugerido al crear settings; no es regla de negocio."""
    return timezone.localdate().year


def default_max_images_warning_threshold():
    """Umbral recomendado de imágenes antes de avisar al usuario."""
    return getattr(settings, "DOCX_MAX_IMAGES_WARNING_THRESHOLD", 50)


def default_block_documents_over_image_limit():
    """Control explícito para convertir el umbral recomendado en bloqueo."""
    return getattr(settings, "DOCX_BLOCK_DOCUMENTS_OVER_IMAGE_LIMIT", False)


class ProcessRun(models.Model):
    """Unidad principal de trazabilidad del flujo de procesamiento.

    Representa una corrida completa del pipeline, incluyendo documento origen,
    estado de ejecución, contadores y artefactos generados.
    """

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_ERRORS = "completed_with_errors", "Completed with errors"
        FAILED = "failed", "Failed"

    source_docx = models.FileField(upload_to="process_runs/%Y/%m/%d/documents/")
    original_filename = models.CharField(max_length=255)
    extracted_text = models.TextField(blank=True, default="")
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
    source_docx_hash = models.CharField(max_length=64, blank=True, db_index=True)
    processing_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SourceImage(models.Model):
    """Imagen extraída del DOCX con estado OCR y metadatos asociados.

    Incluye imágenes reales y fuentes técnicas internas usadas para contexto.
    """

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
    """Consignación estructurada derivada de una imagen fuente.

    Mantiene el resultado normalizado que consumen la UI, la exportación Excel
    y las correcciones manuales.
    """

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
    canonical_key = models.CharField(
        max_length=255, blank=True, null=True, db_index=True
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["sequence_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["process_run", "source_image", "canonical_key"],
                name="uniq_deposit_canonical_per_source",
            )
        ]


class ProcessingSettings(models.Model):
    """Singleton de configuración para OCR, LLM y asistente.

    El registro concentra credenciales, proveedor activo y criterios de
    extracción para mantener consistente el runtime del pipeline.
    """

    class OCRMode(models.TextChoices):
        TESSERACT = "tesseract", "Tesseract"
        VISION = "vision", "Vision"
        AUTO = "auto", "Auto"

    class Provider(models.TextChoices):
        OLLAMA = "ollama", "Ollama"
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Gemini"
        DEEPSEEK = "deepseek", "DeepSeek"
        ANTHROPIC = "anthropic", "Anthropic"

    singleton_key = models.CharField(max_length=32, unique=True, default="default")
    ocr_mode = models.CharField(
        max_length=32, choices=OCRMode.choices, default=OCRMode.VISION
    )
    ocr_provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    ocr_model = models.CharField(max_length=128, blank=True)
    vision_model = models.CharField(max_length=128, blank=True)
    llm_provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    llm_model = models.CharField(max_length=128, blank=True)
    assistant_provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.OLLAMA
    )
    assistant_model = models.CharField(max_length=128, blank=True)
    ocr_api_key = models.CharField(max_length=255, blank=True)
    llm_api_key = models.CharField(max_length=255, blank=True)
    assistant_api_key = models.CharField(max_length=255, blank=True)
    assistant_temperature = models.FloatField(default=0.2)
    assistant_num_predict = models.PositiveIntegerField(default=256)
    assistant_show_debug_details = models.BooleanField(default=False)
    request_timeout_seconds = models.PositiveIntegerField(default=320)
    max_images_warning_threshold = models.PositiveIntegerField(
        default=default_max_images_warning_threshold
    )
    block_documents_over_image_limit = models.BooleanField(
        default=default_block_documents_over_image_limit
    )
    valid_consignation_month = models.PositiveSmallIntegerField(
        default=default_valid_consignation_month
    )
    valid_consignation_year = models.PositiveSmallIntegerField(
        default=default_valid_consignation_year
    )
    extraction_criteria = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Processing Settings"
        verbose_name_plural = "Processing Settings"

    def __str__(self):
        return f"ProcessingSettings (singleton: {self.singleton_key})"

    @property
    def effective_ocr_model(self):
        """Devuelve ocr_model o default desde settings."""
        return self.ocr_model or getattr(settings, "OCR_MODEL", "spa")

    @property
    def effective_vision_model(self):
        """Devuelve vision_model o default desde settings."""
        return self.vision_model or getattr(
            settings,
            "VISION_MODEL",
            getattr(settings, "OLLAMA_VISION_MODEL", "gemma4:e2b"),
        )

    @property
    def effective_llm_model(self):
        """Devuelve llm_model o default desde settings."""
        return self.llm_model or getattr(settings, "LLM_MODEL", "qwen2.5:7b")

    @property
    def effective_assistant_model(self):
        """Devuelve assistant_model o default desde settings."""
        return self.assistant_model or getattr(
            settings, "ASSISTANT_MODEL", "qwen2.5:7b"
        )

    @property
    def effective_assistant_temperature(self):
        """Devuelve assistant_temperature o default desde settings."""
        return self.assistant_temperature or getattr(
            settings, "ASSISTANT_TEMPERATURE", 0.2
        )

    @property
    def effective_assistant_num_predict(self):
        """Devuelve assistant_num_predict o default desde settings."""
        return self.assistant_num_predict or getattr(
            settings, "ASSISTANT_NUM_PREDICT", 256
        )


class ExtractionLog(models.Model):
    """Evento técnico de extracción, validación o reproceso.

    Sirve como bitácora de diagnóstico para explicar por qué una etapa
    completó, falló o produjo resultados parciales.
    """

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
