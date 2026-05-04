from django.db import migrations, models

import apps.processing.models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0013_processingsettings_vision_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="processrun",
            name="processing_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="processrun",
            name="source_docx_hash",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="extracteddeposit",
            name="canonical_key",
            field=models.CharField(
                blank=True, db_index=True, max_length=255, null=True
            ),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="block_documents_over_image_limit",
            field=models.BooleanField(
                default=apps.processing.models.default_block_documents_over_image_limit
            ),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="max_images_warning_threshold",
            field=models.PositiveIntegerField(
                default=apps.processing.models.default_max_images_warning_threshold
            ),
        ),
        migrations.AddConstraint(
            model_name="extracteddeposit",
            constraint=models.UniqueConstraint(
                fields=("process_run", "source_image", "canonical_key"),
                name="uniq_deposit_canonical_per_source",
            ),
        ),
    ]
