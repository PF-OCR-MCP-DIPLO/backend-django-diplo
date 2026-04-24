from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
from rest_framework import serializers

from apps.extraction.schemas import ConsignacionBasica
from apps.processing.models import (
    ExtractedDeposit,
    ExtractionLog,
    ProcessingSettings,
    ProcessRun,
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
    has_ocr_api_key = serializers.SerializerMethodField(read_only=True)
    has_llm_api_key = serializers.SerializerMethodField(read_only=True)
    ocr_api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=255
    )
    llm_api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=255
    )

    class Meta:
        model = ProcessingSettings
        fields = [
            "ocr_mode",
            "ocr_provider",
            "ocr_model",
            "llm_provider",
            "llm_model",
            "ocr_api_key",
            "llm_api_key",
            "has_ocr_api_key",
            "has_llm_api_key",
            "request_timeout_seconds",
            "updated_at",
        ]

    def get_has_ocr_api_key(self, obj):
        return bool(obj.ocr_api_key)

    def get_has_llm_api_key(self, obj):
        return bool(obj.llm_api_key)

    def validate(self, attrs):
        instance = self.instance
        ocr_mode = attrs.get("ocr_mode", getattr(instance, "ocr_mode", "vision"))
        ocr_provider = attrs.get(
            "ocr_provider", getattr(instance, "ocr_provider", "ollama")
        )
        llm_provider = attrs.get(
            "llm_provider", getattr(instance, "llm_provider", "ollama")
        )
        ocr_api_key = attrs.get("ocr_api_key", getattr(instance, "ocr_api_key", ""))
        llm_api_key = attrs.get("llm_api_key", getattr(instance, "llm_api_key", ""))
        ocr_model = attrs.get("ocr_model", getattr(instance, "ocr_model", ""))
        llm_model = attrs.get("llm_model", getattr(instance, "llm_model", ""))
        request_timeout_seconds = attrs.get(
            "request_timeout_seconds",
            getattr(instance, "request_timeout_seconds", 320),
        )

        errors = {}
        if request_timeout_seconds < 5 or request_timeout_seconds > 600:
            errors["request_timeout_seconds"] = [
                "Timeout must be between 5 and 600 seconds."
            ]

        if ocr_mode in ("vision", "auto") and ocr_provider != "ollama":
            if not ocr_api_key:
                errors["ocr_api_key"] = [
                    f"OCR provider '{ocr_provider}' requires API key."
                ]
            errors["ocr_provider"] = [
                f"OCR provider '{ocr_provider}' is not operational in this MVP."
            ]
        if ocr_mode in ("vision", "auto") and not ocr_model:
            errors["ocr_model"] = ["OCR model is required for vision/auto mode."]

        if llm_provider != "ollama":
            if not llm_api_key:
                errors["llm_api_key"] = [
                    f"LLM provider '{llm_provider}' requires API key."
                ]
            errors["llm_provider"] = [
                f"LLM provider '{llm_provider}' is not operational in this MVP."
            ]
        if not llm_model:
            errors["llm_model"] = ["LLM model is required."]

        if ocr_mode == "tesseract":
            effective_ocr_model = attrs.get(
                "ocr_model", getattr(instance, "ocr_model", "")
            )
            if not effective_ocr_model or ":" in effective_ocr_model:
                attrs["ocr_model"] = "spa"
            attrs["ocr_provider"] = "ollama"
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AssistantChatSerializer(serializers.Serializer):
    messages = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )
    job_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    jobId = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, write_only=True
    )
    errors = serializers.IntegerField(required=False, min_value=0, default=0)
    query_context = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        camel_job_id = attrs.pop("jobId", None)
        snake_job_id = attrs.get("job_id")
        if (
            camel_job_id is not None
            and snake_job_id is not None
            and camel_job_id != snake_job_id
        ):
            raise serializers.ValidationError(
                {"job_id": "job_id and jobId must reference the same job."}
            )
        if snake_job_id is None and camel_job_id is not None:
            attrs["job_id"] = camel_job_id
        return attrs

    def validate_messages(self, value):
        allowed_roles = {"user", "assistant", "system"}
        cleaned: list[dict[str, str]] = []
        for item in value:
            role = str(item.get("role") or "").strip()
            content = item.get("content")
            if role not in allowed_roles:
                raise serializers.ValidationError(
                    f"Invalid message role '{role}'. Allowed: user, assistant, system."
                )
            if not isinstance(content, str):
                raise serializers.ValidationError(
                    "Each message content must be a string."
                )
            cleaned.append({"role": role, "content": content})
        return cleaned


class BulkDepositCorrectionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    fecha_consignacion = serializers.CharField(allow_blank=True, required=False)
    hora_consignacion = serializers.CharField(allow_blank=True, required=False)
    referencia = serializers.CharField()
    valor = serializers.DecimalField(max_digits=14, decimal_places=2)

    def validate(self, attrs):
        payload = {
            "fecha_consignacion": attrs.get("fecha_consignacion") or None,
            "hora_consignacion": attrs.get("hora_consignacion") or None,
            "referencia": attrs.get("referencia"),
            "valor": attrs.get("valor"),
        }
        try:
            normalized = ConsignacionBasica.model_validate(payload)
        except PydanticValidationError as error:
            raise serializers.ValidationError({"item": error.errors()}) from error

        attrs["fecha_consignacion"] = normalized.fecha_consignacion or ""
        attrs["hora_consignacion"] = normalized.hora_consignacion or ""
        attrs["referencia"] = normalized.referencia
        attrs["valor"] = Decimal(str(normalized.valor)).quantize(Decimal("0.01"))
        return attrs


class BulkDepositCorrectionSerializer(serializers.Serializer):
    items = BulkDepositCorrectionItemSerializer(many=True, allow_empty=False)
