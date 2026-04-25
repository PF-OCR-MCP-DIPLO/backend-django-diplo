from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("processing", "0007_processingsettings_assistant_show_debug_details"),
    ]

    operations = [
        migrations.AlterField(
            model_name="processingsettings",
            name="assistant_provider",
            field=models.CharField(
                choices=[
                    ("ollama", "Ollama"),
                    ("openai", "OpenAI"),
                    ("gemini", "Gemini"),
                    ("deepseek", "DeepSeek"),
                    ("anthropic", "Anthropic"),
                ],
                default="ollama",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="processingsettings",
            name="llm_provider",
            field=models.CharField(
                choices=[
                    ("ollama", "Ollama"),
                    ("openai", "OpenAI"),
                    ("gemini", "Gemini"),
                    ("deepseek", "DeepSeek"),
                    ("anthropic", "Anthropic"),
                ],
                default="ollama",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="processingsettings",
            name="ocr_provider",
            field=models.CharField(
                choices=[
                    ("ollama", "Ollama"),
                    ("openai", "OpenAI"),
                    ("gemini", "Gemini"),
                    ("deepseek", "DeepSeek"),
                    ("anthropic", "Anthropic"),
                ],
                default="ollama",
                max_length=32,
            ),
        ),
    ]
