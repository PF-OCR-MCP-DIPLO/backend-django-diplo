"""Esquemas Pydantic para consignaciones estructuradas por LLM."""

import re

from pydantic import BaseModel, Field, field_validator
from apps.common.utils.time import normalize_time_24h
from apps.common.utils.currency import smart_parse_currency

MONTH_ALIASES = {
    "ene": 1,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
    "dec": 12,
}


class ConsignacionBasica(BaseModel):
    """Representa una consignación validada por el contrato del extractor."""

    fecha_consignacion: str | None = Field(default=None)
    hora_consignacion: str | None = Field(default=None)
    referencia: str
    valor: float
    remitente: str | None = Field(default=None)
    telefono_remitente: str | None = Field(default=None)
    empresa_origen: str | None = Field(default=None)

    @field_validator("fecha_consignacion")
    @classmethod
    def validate_fecha(cls, value):
        if not value or str(value).lower() == "null":
            return None
        value = value.strip()
        month_match = re.match(
            r"^(?P<day>\d{1,2})[/-](?P<month>[A-Za-zÁÉÍÓÚáéíóú]{3,})[/-](?P<year>\d{2,4})$",
            value,
        )
        if month_match:
            month_key = month_match.group("month").lower()[:4]
            month = MONTH_ALIASES.get(month_key) or MONTH_ALIASES.get(month_key[:3])
            if month:
                year = int(month_match.group("year"))
                if year < 100:
                    year += 2000
                return f"{int(month_match.group('day')):02d}/{month:02d}/{year:04d}"
        if not re.match(r"^\d{2}/\d{2}/\d{4}$", value):
            raise ValueError("fecha_consignacion must be DD/MM/YYYY")
        return value

    @field_validator("hora_consignacion")
    @classmethod
    def validate_hora(cls, value):
        return normalize_time_24h(value)

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

    @field_validator("remitente")
    @classmethod
    def validate_remitente(cls, value):
        if not value or str(value).lower() in {"null", "none", "", "n/a"}:
            return None
        return str(value).strip()

    @field_validator("remitente", "telefono_remitente", "empresa_origen")
    @classmethod
    def validate_optional_text(cls, value):
        if value is None:
            return None

        text = str(value).strip()
        if not text or text.lower() in {"null", "none", "n/a", "na", ""}:
            return None

        return text


class ListaConsignaciones(BaseModel):
    """Contenedor principal devuelto por el proveedor de estructuración."""

    consignaciones: list[ConsignacionBasica]
