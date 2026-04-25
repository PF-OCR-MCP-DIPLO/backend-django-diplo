from __future__ import annotations

from pydantic import BaseModel, Field


class UploadDocumentInput(BaseModel):
    file_path: str = Field(description="Absolute path to the .docx file")


class JobIdInput(BaseModel):
    job_id: int = Field(ge=1, description="Identifier of the processing job")


class UpdateProcessingSettingsInput(BaseModel):
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

    def to_partial_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


class DepositCorrectionInput(BaseModel):
    job_id: int = Field(ge=1, description="Identifier of the processing job")
    deposit_id: int = Field(ge=1, description="Identifier of the extracted deposit")
    fecha_consignacion: str | None = None
    hora_consignacion: str | None = None
    referencia: str
    valor: float
