"""Esquemas Pydantic para entradas de herramientas MCP."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class UploadDocumentInput(BaseModel):
    """Entrada para subir documentos desde una ruta local."""

    file_path: str = Field(description="Absolute path to the .docx file")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("file_path must be absolute")
        if path.suffix.lower() != ".docx":
            raise ValueError("Only .docx files are supported")
        return value


class JobIdInput(BaseModel):
    """Entrada mínima para herramientas que operan sobre un job."""

    job_id: int = Field(ge=1, description="Identifier of the processing job")


class ReprocessSourceInput(BaseModel):
    """Entrada para reprocesar una fuente o el origen de un depósito."""

    job_id: int = Field(ge=1, description="Identifier of the processing job")
    source_image_id: int | None = Field(
        default=None, ge=1, description="Source image to reprocess"
    )
    deposit_id: int | None = Field(
        default=None,
        ge=1,
        description="Deposit whose source image should be reprocessed",
    )

    @field_validator("deposit_id")
    @classmethod
    def validate_target(cls, value, info):
        """Exige al menos un objetivo de reproceso para evitar llamadas ambiguas."""
        source_image_id = info.data.get("source_image_id")
        if value is None and source_image_id is None:
            raise ValueError("source_image_id or deposit_id is required")
        return value


class UpdateProcessingSettingsInput(BaseModel):
    """Entrada parcial para aplicar ajustes de configuración."""

    ocr_mode: str | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    assistant_provider: str | None = None
    assistant_model: str | None = None
    assistant_api_key: str | None = None
    assistant_temperature: float | None = None
    assistant_num_predict: int | None = None
    ocr_api_key: str | None = None
    llm_api_key: str | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    assistant_show_debug_details: bool | None = None

    def to_partial_dict(self) -> dict:
        """Exporta solo campos presentes para aplicar patch parcial idempotente."""
        return self.model_dump(exclude_none=True)


class AssistantChatMessageInput(BaseModel):
    """Mensaje individual enviado al asistente por MCP."""

    role: str
    content: str


class AssistantChatInput(BaseModel):
    """Payload del chat del asistente en el contrato MCP."""

    messages: list[AssistantChatMessageInput]
    job_id: int | None = Field(default=None, ge=1)
    errors: int = Field(default=0, ge=0)
    query_context: dict = Field(default_factory=dict)


class DepositCorrectionInput(BaseModel):
    """Entrada para corregir una consignación desde una herramienta MCP."""

    job_id: int = Field(ge=1, description="Identifier of the processing job")
    deposit_id: int = Field(ge=1, description="Identifier of the extracted deposit")
    fecha_consignacion: str | None = None
    hora_consignacion: str | None = None
    referencia: str
    valor: float
