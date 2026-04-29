from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0010_normalize_ocr_provider_values"),
    ]

    operations = [
        migrations.AlterField(
            model_name="extracteddeposit",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
