import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ProcessRun",
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
                    "source_docx",
                    models.FileField(upload_to="process_runs/%Y/%m/%d/documents/"),
                ),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("uploaded", "Uploaded"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="uploaded",
                        max_length=32,
                    ),
                ),
                ("total_images", models.PositiveIntegerField(default=0)),
                ("total_records", models.PositiveIntegerField(default=0)),
                (
                    "excel_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to="process_runs/%Y/%m/%d/exports/",
                    ),
                ),
                ("error_message", models.TextField(blank=True)),
                (
                    "provider_config_snapshot",
                    models.JSONField(blank=True, default=dict),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="SourceImage",
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
                ("sequence_index", models.PositiveIntegerField()),
                (
                    "image_file",
                    models.FileField(upload_to="process_runs/%Y/%m/%d/images/"),
                ),
                ("source_name", models.CharField(max_length=255)),
                ("content_hash", models.CharField(blank=True, max_length=64)),
                (
                    "ocr_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processed", "Processed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("ocr_raw_text", models.TextField(blank=True)),
                ("ocr_provider", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "process_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="source_images",
                        to="processing.processrun",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence_index", "id"],
                "unique_together": {("process_run", "sequence_index")},
            },
        ),
        migrations.CreateModel(
            name="ExtractedDeposit",
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
                ("sequence_index", models.PositiveIntegerField()),
                ("fecha_consignacion", models.CharField(blank=True, max_length=10)),
                ("hora_consignacion", models.CharField(blank=True, max_length=5)),
                ("referencia", models.CharField(max_length=255)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=14)),
                ("is_current_month", models.BooleanField(blank=True, null=True)),
                ("observations", models.JSONField(blank=True, default=list)),
                ("structured_payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "process_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deposits",
                        to="processing.processrun",
                    ),
                ),
                (
                    "source_image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deposits",
                        to="processing.sourceimage",
                    ),
                ),
            ],
            options={
                "ordering": ["sequence_index", "id"],
            },
        ),
    ]
