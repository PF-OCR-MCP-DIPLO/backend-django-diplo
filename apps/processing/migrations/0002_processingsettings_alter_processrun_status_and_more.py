import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessingSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "singleton_key",
                    models.CharField(default="default", max_length=32, unique=True),
                ),
                (
                    "ocr_mode",
                    models.CharField(
                        choices=[
                            ("tesseract", "Tesseract"),
                            ("vision", "Vision"),
                            ("auto", "Auto"),
                        ],
                        default="vision",
                        max_length=32,
                    ),
                ),
                (
                    "ocr_provider",
                    models.CharField(
                        choices=[
                            ("ollama", "Ollama"),
                            ("openai", "OpenAI"),
                            ("gemini", "Gemini"),
                            ("deepseek", "DeepSeek"),
                        ],
                        default="ollama",
                        max_length=32,
                    ),
                ),
                ("ocr_model", models.CharField(blank=True, max_length=128)),
                (
                    "llm_provider",
                    models.CharField(
                        choices=[
                            ("ollama", "Ollama"),
                            ("openai", "OpenAI"),
                            ("gemini", "Gemini"),
                            ("deepseek", "DeepSeek"),
                        ],
                        default="ollama",
                        max_length=32,
                    ),
                ),
                ("llm_model", models.CharField(blank=True, max_length=128)),
                ("request_timeout_seconds", models.PositiveIntegerField(default=320)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AlterField(
            model_name="processrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("uploaded", "Uploaded"),
                    ("processing", "Processing"),
                    ("completed", "Completed"),
                    ("completed_with_errors", "Completed with errors"),
                    ("failed", "Failed"),
                ],
                default="uploaded",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="ExtractionLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("sequence_index", models.PositiveIntegerField(default=0)),
                ("stage", models.CharField(max_length=64)),
                ("provider", models.CharField(blank=True, max_length=64)),
                ("model", models.CharField(blank=True, max_length=128)),
                ("ocr_mode", models.CharField(blank=True, max_length=32)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("raw_text", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("is_error", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "process_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction_logs",
                        to="processing.processrun",
                    ),
                ),
                (
                    "source_image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extraction_logs",
                        to="processing.sourceimage",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence_index", "id"],
            },
        ),
    ]
