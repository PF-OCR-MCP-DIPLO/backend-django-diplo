from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0005_processingsettings_assistant_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingsettings",
            name="extraction_criteria",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
