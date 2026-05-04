from django.conf import settings
from django.db import migrations, models

TESSERACT_MODELS = {"spa", "eng", "spa+eng"}


def split_legacy_ocr_model(apps, schema_editor):
    ProcessingSettings = apps.get_model("processing", "ProcessingSettings")
    default_ocr_model = getattr(settings, "OCR_MODEL", "spa")
    default_vision_model = getattr(
        settings,
        "VISION_MODEL",
        getattr(settings, "OLLAMA_VISION_MODEL", "gemma4:e2b"),
    )
    for item in ProcessingSettings.objects.all():
        legacy_model = (item.ocr_model or "").strip()
        if legacy_model and legacy_model not in TESSERACT_MODELS:
            item.vision_model = legacy_model
            item.ocr_model = default_ocr_model
        elif not item.vision_model:
            item.vision_model = default_vision_model
        if not item.ocr_model:
            item.ocr_model = default_ocr_model
        item.save(update_fields=["ocr_model", "vision_model"])


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0012_processingsettings_valid_consignation_month_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingsettings",
            name="vision_model",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.RunPython(split_legacy_ocr_model, migrations.RunPython.noop),
    ]
