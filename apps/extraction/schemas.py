import re

from pydantic import BaseModel, Field, field_validator

from apps.common.utils.currency import smart_parse_currency


class ConsignacionBasica(BaseModel):
    fecha_consignacion: str | None = Field(default=None)
    hora_consignacion: str | None = Field(default=None)
    referencia: str
    valor: float

    @field_validator("fecha_consignacion")
    @classmethod
    def validate_fecha(cls, value):
        if not value or str(value).lower() == "null":
            return None
        value = value.strip()
        if not re.match(r"^\d{2}/\d{2}/\d{4}$", value):
            raise ValueError("fecha_consignacion must be DD/MM/YYYY")
        return value

    @field_validator("hora_consignacion")
    @classmethod
    def validate_hora(cls, value):
        if not value or str(value).lower() == "null":
            return None
        value = value.strip()
        if not re.match(r"^\d{2}:\d{2}$", value):
            raise ValueError("hora_consignacion must be HH:MM")
        return value

    @field_validator("referencia")
    @classmethod
    def validate_referencia(cls, value):
        if not value or str(value).lower() in {"null", "none", "", "n/a"}:
            raise ValueError("referencia is required")
        value = value.strip()
        banned_words = {
            "pago exitoso",
            "transferencia exitosa",
            "quiero hacerlo",
            "aceptar",
            "enviar",
            "finalizar",
            "volver al inicio",
            "comprobante no.",
            "continuar",
            "descargar",
        }
        lowered = value.lower()
        for banned in banned_words:
            if banned in lowered:
                raise ValueError("referencia is invalid")
        if len(value) < 3:
            raise ValueError("referencia is too short")
        return value

    # Pydantic (v2) tries to parse `float` before validators by default.
    # We need `mode="before"` to normalize LatAm/ES currency strings like "50.000,00"
    # into a number first, otherwise validation fails early.
    @field_validator("valor", mode="before")
    @classmethod
    def validate_valor(cls, value):
        if not value or str(value).lower() in {"null", "none", ""}:
            raise ValueError("valor is required")
        parsed = smart_parse_currency(value)
        if parsed is None or parsed <= 0:
            raise ValueError("valor is invalid")
        return parsed


class ListaConsignaciones(BaseModel):
    consignaciones: list[ConsignacionBasica]
