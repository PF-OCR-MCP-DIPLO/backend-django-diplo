from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0002_processingsettings_alter_processrun_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingsettings",
            name="llm_api_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="ocr_api_key",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
