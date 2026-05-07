"""Utilidades para normalizar horas de consignaciones."""

from __future__ import annotations

import re

_MERIDIEM_TIME_RE = re.compile(
    r"\b(?P<hour>\d{1,2})\s*[:.hH]\s*(?P<minute>\d{2})(?:\s*(?P<second>\d{2}))?\s*(?P<meridiem>a\.?\s*m\.?|p\.?\s*m\.?|am|pm)\b",
    re.IGNORECASE,
)

_TIME_24H_RE = re.compile(
    r"\b(?P<hour>\d{1,2})\s*[:.hH]\s*(?P<minute>\d{2})(?:\s*[:.hH]\s*(?P<second>\d{2}))?\b",
    re.IGNORECASE,
)


def normalize_meridiem_markers(value: object) -> str:
    """Preserva AM/PM aunque venga como 'a. m.' o 'p. m.'."""
    text = str(value or "")
    text = re.sub(r"\ba\s*\.?\s*m\.?\b", "am", text, flags=re.IGNORECASE)
    text = re.sub(r"\bp\s*\.?\s*m\.?\b", "pm", text, flags=re.IGNORECASE)
    return text


def normalize_time_24h(value: object) -> str | None:
    """Convierte horas 12h/24h a HH:MM.

    Ejemplos:
    - 2:00 pm -> 14:00
    - 2:00 p. m. -> 14:00
    - 12:00 am -> 00:00
    - 12:00 pm -> 12:00
    - 11:49 a. m. -> 11:49
    - 10:13:03 -> 10:13
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return None

    normalized = normalize_meridiem_markers(text).lower()

    meridiem_match = _MERIDIEM_TIME_RE.search(normalized)
    if meridiem_match:
        hour = int(meridiem_match.group("hour"))
        minute = int(meridiem_match.group("minute"))
        meridiem = meridiem_match.group("meridiem").lower()

        if not (1 <= hour <= 12 and 0 <= minute <= 59):
            raise ValueError("hora_consignacion has invalid 12-hour time")

        if meridiem == "am":
            hour = 0 if hour == 12 else hour
        elif meridiem == "pm":
            hour = 12 if hour == 12 else hour + 12

        return f"{hour:02d}:{minute:02d}"

    match = _TIME_24H_RE.search(normalized)
    if match:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    raise ValueError("hora_consignacion must be HH:MM")
