from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0004_processrun_extracted_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_api_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_model",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_num_predict",
            field=models.PositiveIntegerField(default=256),
        ),
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_provider",
            field=models.CharField(
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
        migrations.AddField(
            model_name="processingsettings",
            name="assistant_temperature",
            field=models.FloatField(default=0.2),
        ),
    ]
