from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0006_processingsettings_extraction_criteria"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_show_debug_details",
            field=models.BooleanField(default=False),
        ),
    ]
