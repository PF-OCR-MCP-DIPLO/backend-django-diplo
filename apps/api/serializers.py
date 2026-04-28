"""Serializers REST del backend de consignaciones.

Transforman modelos y payloads de entrada en contratos estables para la API.
"""

import json
from decimal import Decimal

from django.conf import settings
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
from apps.processing.services.extraction_criteria import normalize_extraction_criteria
from apps.processing.services.provider_normalization import normalize_ocr_provider

OCR_PROVIDER_VALUES = {"ollama", "openai", "gemini", "deepseek"}
LLM_PROVIDER_VALUES = {"ollama", "openai", "gemini", "deepseek", "anthropic"}


class UploadDocumentSerializer(serializers.Serializer):
    """Valida la carga de un archivo `.docx` antes de crear una corrida."""

    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.lower().endswith(".docx"):
            raise serializers.ValidationError("Only .docx files are supported.")
        max_size = int(getattr(settings, "DOCX_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
        if getattr(value, "size", 0) > max_size:
            raise serializers.ValidationError(
                f"File exceeds maximum allowed size of {max_size} bytes."
            )
        return value


class ExtractedDepositSerializer(serializers.ModelSerializer):
    """Expone una consignación extraída o corregida para la UI y exportación."""

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
    """Representa una imagen fuente del DOCX junto con sus depósitos."""

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
    """Serializer resumido para listados de corridas en historial."""

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
    """Serializer detallado de una corrida con relaciones anidadas."""

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
    """Serializer de trazas técnicas por etapa de extracción o reproceso."""

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
    """Serializer del singleton de configuración de procesamiento.

    Oculta claves reales al serializar, expone banderas de presencia y valida
    combinaciones de proveedor/modo según lo que soporta este MVP.
    """

    has_ocr_api_key = serializers.SerializerMethodField(read_only=True)
    has_llm_api_key = serializers.SerializerMethodField(read_only=True)
    has_assistant_api_key = serializers.SerializerMethodField(read_only=True)
    ocr_provider = serializers.CharField(required=False)
    ocr_api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=255
    )
    llm_api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=255
    )
    assistant_api_key = serializers.CharField(
        required=False, allow_blank=True, write_only=True, max_length=255
    )
    extraction_criteria = serializers.JSONField(required=False)
    assistant_show_debug_details = serializers.BooleanField(required=False)

    class Meta:
        model = ProcessingSettings
        fields = [
            "ocr_mode",
            "ocr_provider",
            "ocr_model",
            "llm_provider",
            "llm_model",
            "assistant_provider",
            "assistant_model",
            "ocr_api_key",
            "llm_api_key",
            "assistant_api_key",
            "extraction_criteria",
            "assistant_show_debug_details",
            "has_ocr_api_key",
            "has_llm_api_key",
            "has_assistant_api_key",
            "assistant_temperature",
            "assistant_num_predict",
            "request_timeout_seconds",
            "updated_at",
        ]

    def get_has_ocr_api_key(self, obj):
        return bool(obj.ocr_api_key)

    def get_has_llm_api_key(self, obj):
        return bool(obj.llm_api_key)

    def get_has_assistant_api_key(self, obj):
        return bool(obj.assistant_api_key)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["extraction_criteria"] = normalize_extraction_criteria(
            data.get("extraction_criteria")
        )
        return data

    def validate_ocr_provider(self, value):
        """Acepta aliases legacy y los persiste en forma canónica."""
        return normalize_ocr_provider(value)

    def validate(self, attrs):
        instance = self.instance
        ocr_mode = attrs.get("ocr_mode", getattr(instance, "ocr_mode", "vision"))
        ocr_provider = attrs.get(
            "ocr_provider", getattr(instance, "ocr_provider", "ollama")
        )
        ocr_provider = normalize_ocr_provider(ocr_provider)
        attrs["ocr_provider"] = ocr_provider
        llm_provider = attrs.get(
            "llm_provider", getattr(instance, "llm_provider", "ollama")
        )
        assistant_provider = attrs.get(
            "assistant_provider", getattr(instance, "assistant_provider", "ollama")
        )
        ocr_api_key = attrs.get("ocr_api_key", getattr(instance, "ocr_api_key", ""))
        llm_api_key = attrs.get("llm_api_key", getattr(instance, "llm_api_key", ""))
        assistant_api_key = attrs.get(
            "assistant_api_key", getattr(instance, "assistant_api_key", "")
        )
        ocr_model = attrs.get("ocr_model", getattr(instance, "ocr_model", ""))
        llm_model = attrs.get("llm_model", getattr(instance, "llm_model", ""))
        assistant_model = attrs.get(
            "assistant_model", getattr(instance, "assistant_model", "")
        )
        assistant_show_debug_details = attrs.get(
            "assistant_show_debug_details",
            getattr(instance, "assistant_show_debug_details", False),
        )
        extraction_criteria = attrs.get(
            "extraction_criteria", getattr(instance, "extraction_criteria", {})
        )
        request_timeout_seconds = attrs.get(
            "request_timeout_seconds",
            getattr(instance, "request_timeout_seconds", 320),
        )

        errors = {}
        if request_timeout_seconds < 5 or request_timeout_seconds > 600:
            errors["request_timeout_seconds"] = [
                "Timeout must be between 5 and 600 seconds."
            ]
        if ocr_provider not in OCR_PROVIDER_VALUES:
            errors["ocr_provider"] = [
                f"OCR provider '{ocr_provider}' is not supported for OCR."
            ]
        if llm_provider not in LLM_PROVIDER_VALUES:
            errors["llm_provider"] = [
                f"LLM provider '{llm_provider}' is not supported."
            ]
        if assistant_provider not in LLM_PROVIDER_VALUES:
            errors["assistant_provider"] = [
                f"Assistant provider '{assistant_provider}' is not supported."
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

        if assistant_provider == "ollama" and not assistant_model:
            errors["assistant_model"] = [
                "Assistant model is required when assistant_provider is ollama."
            ]
        if assistant_provider != "ollama":
            if not assistant_api_key:
                errors["assistant_api_key"] = [
                    f"Assistant provider '{assistant_provider}' requires API key."
                ]
            errors["assistant_provider"] = [
                f"Assistant provider '{assistant_provider}' is not operational in this MVP."
            ]

        if ocr_mode == "tesseract":
            attrs["ocr_provider"] = "ollama"
            effective_ocr_model = attrs.get(
                "ocr_model", getattr(instance, "ocr_model", "")
            )
            if not effective_ocr_model or ":" in effective_ocr_model:
                attrs["ocr_model"] = "spa"
        if errors:
            raise serializers.ValidationError(errors)
        attrs["extraction_criteria"] = normalize_extraction_criteria(
            extraction_criteria
        )
        attrs["assistant_show_debug_details"] = bool(assistant_show_debug_details)
        return attrs


class AssistantChatSerializer(serializers.Serializer):
    """Valida payload de chat del asistente con límites de seguridad.

    Admite `job_id` y `jobId` como alias para compatibilidad de clientes.
    """

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
    max_messages = 20
    max_message_length = 4000
    max_query_context_chars = 4000

    def validate(self, attrs):
        """Normaliza alias de identificador de job y evita conflictos de entrada."""
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
        """Restringe cardinalidad, roles y tamaño de mensajes del historial."""
        if len(value) > self.max_messages:
            raise serializers.ValidationError(
                f"No more than {self.max_messages} messages are allowed."
            )
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
            if len(content) > self.max_message_length:
                raise serializers.ValidationError(
                    f"Each message content must be at most {self.max_message_length} characters."
                )
            cleaned.append({"role": role, "content": content})
        return cleaned

    def validate_query_context(self, value):
        """Controla tamaño y profundidad para evitar payloads abusivos."""
        serialized = json.dumps(value)
        if len(serialized) > self.max_query_context_chars:
            raise serializers.ValidationError("query_context is too large.")
        if self._nesting_depth(value) > 4:
            raise serializers.ValidationError("query_context nesting is too deep.")
        return value

    def _nesting_depth(self, value, current=0):
        if isinstance(value, dict):
            if len(value) > 20:
                return current + 10
            return max(
                [current]
                + [self._nesting_depth(item, current + 1) for item in value.values()]
            )
        if isinstance(value, list):
            if len(value) > 20:
                return current + 10
            return max(
                [current] + [self._nesting_depth(item, current + 1) for item in value]
            )
        return current


class BulkDepositCorrectionItemSerializer(serializers.Serializer):
    """Valida una fila de corrección manual de consignación."""

    id = serializers.IntegerField(min_value=1)
    fecha_consignacion = serializers.CharField(allow_blank=True, required=False)
    hora_consignacion = serializers.CharField(allow_blank=True, required=False)
    referencia = serializers.CharField()
    valor = serializers.DecimalField(max_digits=14, decimal_places=2)

    def validate(self, attrs):
        """Aplica validación estructural usando schema Pydantic canónico."""
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
    """Envuelve lote de correcciones para actualización masiva por job."""

    items = BulkDepositCorrectionItemSerializer(many=True, allow_empty=False)


class DepositCorrectionSerializer(BulkDepositCorrectionItemSerializer):
    """Compatibilidad histórica para payload de corrección con `job_id`."""

    job_id = serializers.IntegerField(min_value=1)
