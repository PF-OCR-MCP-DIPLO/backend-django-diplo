from copy import deepcopy

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
    return deepcopy(DEFAULT_EXTRACTION_CRITERIA)


def normalize_extraction_criteria(value):
    if not isinstance(value, dict):
        return default_extraction_criteria()

    fields = value.get("fields")
    if not isinstance(fields, list) or not fields:
        return default_extraction_criteria()

    normalized_fields = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        normalized_fields.append(
            {
                "key": str(field.get("key") or "").strip(),
                "label": str(field.get("label") or field.get("key") or "").strip(),
                "type": str(field.get("type") or "text").strip(),
                "required": bool(field.get("required", False)),
                "enabled": bool(field.get("enabled", True)),
                "expectedValue": field.get("expectedValue"),
                "validationRules": (
                    field.get("validationRules")
                    if isinstance(field.get("validationRules"), list)
                    else []
                ),
                "helpText": field.get("helpText") or "",
                "order": int(field.get("order") or index + 1),
            }
        )

    normalized_fields = [field for field in normalized_fields if field["key"]]
    normalized_fields.sort(key=lambda item: item.get("order", 0))
    return {"fields": normalized_fields or default_extraction_criteria()["fields"]}
