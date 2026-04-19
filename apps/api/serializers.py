from rest_framework import serializers

from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessRun,
    ProcessingSettings,
    SourceImage,
)


class UploadDocumentSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.lower().endswith(".docx"):
            raise serializers.ValidationError("Only .docx files are supported.")
        return value


class ExtractedDepositSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractedDeposit
        fields = [
            "id",
            "sequence_index",
            "fecha_consignacion",
            "hora_consignacion",
            "referencia",
            "valor",
            "is_current_month",
            "observations",
            "structured_payload",
            "created_at",
        ]


class SourceImageSerializer(serializers.ModelSerializer):
    deposits = ExtractedDepositSerializer(many=True, read_only=True)
    image_file = serializers.FileField(read_only=True)

    class Meta:
        model = SourceImage
        fields = [
            "id",
            "sequence_index",
            "source_name",
            "content_hash",
            "ocr_status",
            "ocr_provider",
            "ocr_raw_text",
            "error_message",
            "image_file",
            "deposits",
            "created_at",
            "updated_at",
        ]


class ProcessRunListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessRun
        fields = [
            "id",
            "original_filename",
            "status",
            "total_images",
            "total_records",
            "started_at",
            "finished_at",
            "created_at",
        ]


class ProcessRunDetailSerializer(serializers.ModelSerializer):
    source_images = SourceImageSerializer(many=True, read_only=True)
    source_docx = serializers.FileField(read_only=True)
    excel_file = serializers.FileField(read_only=True)

    class Meta:
        model = ProcessRun
        fields = [
            "id",
            "original_filename",
            "status",
            "source_docx",
            "excel_file",
            "total_images",
            "total_records",
            "error_message",
            "provider_config_snapshot",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
            "source_images",
        ]


class ExtractionLogSerializer(serializers.ModelSerializer):
    source_image_id = serializers.IntegerField(source="source_image.id", read_only=True)

    class Meta:
        model = ExtractionLog
        fields = [
            "id",
            "source_image_id",
            "sequence_index",
            "stage",
            "provider",
            "model",
            "ocr_mode",
            "raw_payload",
            "raw_text",
            "notes",
            "is_error",
            "created_at",
        ]


class ProcessingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingSettings
        fields = [
            "ocr_mode",
            "ocr_provider",
            "ocr_model",
            "llm_provider",
            "llm_model",
            "request_timeout_seconds",
            "updated_at",
        ]
