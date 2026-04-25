from datetime import datetime

from django.utils import timezone


def _field_value(record, field_name):
    if not isinstance(record, dict):
        return None
    return record.get(field_name)


def _validate_criteria_rules(record, criteria):
    observations = []
    if not isinstance(criteria, dict):
        return observations

    fields = criteria.get("fields") or []
    for field in fields:
        if not isinstance(field, dict) or not field.get("enabled", True):
            continue

        key = field.get("key")
        label = field.get("label") or key
        value = _field_value(record, key)
        rules = field.get("validationRules") or []
        required = bool(field.get("required", False))

        if required and (value is None or value == ""):
            observations.append(f"{label} es obligatorio")
            continue

        if value in (None, ""):
            continue

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            kind = rule.get("kind")
            message = rule.get("message") or f"{label} no es valido"
            if kind == "required" and (value is None or value == ""):
                observations.append(message)
            elif kind == "equals" and value != rule.get("value"):
                observations.append(message)
            elif kind == "regex":
                import re

                pattern = rule.get("pattern") or ""
                if pattern and not re.search(pattern, str(value)):
                    observations.append(message)
            elif kind == "min":
                try:
                    if float(value) < float(rule.get("value")):
                        observations.append(message)
                except (TypeError, ValueError):
                    observations.append(message)
            elif kind == "max":
                try:
                    if float(value) > float(rule.get("value")):
                        observations.append(message)
                except (TypeError, ValueError):
                    observations.append(message)
    return observations


def build_record_observations(fecha_consignacion, record=None, criteria=None):
    observations = []
    if not fecha_consignacion:
        observations.append("Fecha no identificada")
        observations.extend(_validate_criteria_rules(record or {}, criteria))
        return observations, None
    try:
        extracted_date = datetime.strptime(fecha_consignacion, "%d/%m/%Y").date()
    except ValueError:
        observations.append("Fecha invalida")
        observations.extend(_validate_criteria_rules(record or {}, criteria))
        return observations, None
    today = timezone.localdate()
    is_current_month = (
        extracted_date.month == today.month and extracted_date.year == today.year
    )
    if not is_current_month:
        observations.append("Fecha fuera del mes actual")
    observations.extend(_validate_criteria_rules(record or {}, criteria))
    return observations, is_current_month
