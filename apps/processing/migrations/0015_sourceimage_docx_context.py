from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0014_image_limit_idempotency_and_deposit_canonical"),
    ]

    operations = [
        migrations.AddField(
            model_name="sourceimage",
            name="context_date",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="sourceimage",
            name="context_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="sourceimage",
            name="context_text",
            field=models.TextField(blank=True),
        ),
    ]
