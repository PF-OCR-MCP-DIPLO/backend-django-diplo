"""Normalización y validación de criterios de extracción."""

import json
from copy import deepcopy

ALLOWED_FIELD_TYPES = {"text", "number", "date", "currency", "boolean"}

DEFAULT_EXTRACTION_CRITERIA = {
    "fields": [
        {
            "key": "fecha_consignacion",
            "label": "Fecha de consignacion",
            "type": "date",
            "required": True,
            "enabled": True,
            "expectedValue": None,
            "validationRules": [
                {
                    "kind": "required",
                    "message": "La fecha de consignacion es obligatoria.",
                },
            ],
            "helpText": "Fecha de la consignacion en formato DD/MM/YYYY.",
            "order": 1,
        },
        {
            "key": "hora_consignacion",
            "label": "Hora de consignacion",
            "type": "text",
            "required": False,
            "enabled": True,
            "expectedValue": None,
            "validationRules": [],
            "helpText": "Hora capturada para la consignacion en formato HH:MM.",
            "order": 2,
        },
        {
            "key": "referencia",
            "label": "Referencia",
            "type": "text",
            "required": True,
            "enabled": True,
            "expectedValue": None,
            "validationRules": [
                {"kind": "required", "message": "La referencia es obligatoria."},
            ],
            "helpText": "Texto identificador del deposito.",
            "order": 3,
        },
        {
            "key": "valor",
            "label": "Valor",
            "type": "currency",
            "required": True,
            "enabled": True,
            "expectedValue": None,
            "validationRules": [
                {"kind": "required", "message": "El valor es obligatorio."},
            ],
            "helpText": "Monto monetario de la consignacion.",
            "order": 4,
        },
    ]
}


def default_extraction_criteria():
    """Devuelve una copia profunda de los criterios base."""
    return deepcopy(DEFAULT_EXTRACTION_CRITERIA)


def _normalize_validation_rules(value):
    if not isinstance(value, list):
        return []
    normalized_rules = []
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        normalized_rules.append(
            {
                "kind": kind,
                "message": str(item.get("message") or "").strip(),
            }
        )
    return normalized_rules


def _normalize_expected_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def normalize_extraction_criteria(value):
    """Convierte criterios libres en una estructura segura y estable."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default_extraction_criteria()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return default_extraction_criteria()

    if not isinstance(value, dict):
        return default_extraction_criteria()

    fields = value.get("fields")
    if fields is None:
        fields = []
    if not isinstance(fields, list):
        return default_extraction_criteria()

    normalized_fields = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        raw_key = str(field.get("key") or "").strip()
        key = raw_key or f"field_{index + 1}"
        field_type = str(field.get("type") or "text").strip().lower()
        if field_type not in ALLOWED_FIELD_TYPES:
            field_type = "text"
        normalized_fields.append(
            {
                "key": key,
                "label": str(field.get("label") or key).strip(),
                "type": field_type,
                "required": bool(field.get("required", False)),
                "enabled": bool(field.get("enabled", True)),
                "expectedValue": _normalize_expected_value(field.get("expectedValue")),
                "validationRules": _normalize_validation_rules(
                    field.get("validationRules")
                ),
                "helpText": str(field.get("helpText") or "").strip(),
                "order": int(field.get("order") or index + 1),
            }
        )

    normalized_fields.sort(key=lambda item: item.get("order", 0))
    return {"fields": normalized_fields or default_extraction_criteria()["fields"]}
