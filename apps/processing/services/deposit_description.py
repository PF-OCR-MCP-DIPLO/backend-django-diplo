"""Reglas de descripcion contable para consignaciones."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

NEQUI_LABEL = "NEQUI"
CUENTA_LABEL = "CUENTA"
NINGUNO_LABEL = "NINGUNO"

DAVID_GUEVARA_CANONICAL = "DAVID GUEVARA"
DYD_CANONICAL = "GROUP DYD COMUNICACIONES SAS"
NEQUI_PHONE = "3176771287"

DYD_KEYWORDS = {
    "GROUP",
    "GRUPO",
    "DYD",
    "D Y D",
    "COMUNICACIONES",
    "COMUNICACION",
    "SAS",
    "S.A.S",
}


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().upper()
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_accents).strip()


def _digits_only(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _contains_david_guevara(text: str) -> bool:
    normalized = _normalize_text(text)
    if DAVID_GUEVARA_CANONICAL in normalized:
        return True

    # Tolerancia para OCR: DAV1D, GUEBARA, espacios raros, etc.
    compact = normalized.replace(" ", "")
    return _similarity(compact, DAVID_GUEVARA_CANONICAL.replace(" ", "")) >= 0.88


def _contains_nequi_phone(text: str) -> bool:
    return NEQUI_PHONE in _digits_only(text)


def _contains_dyd_variant(text: str) -> bool:
    raw = str(text or "").upper()
    normalized = _normalize_text(raw)

    compact = re.sub(r"[^A-Z0-9]", "", normalized)
    canonical_compact = re.sub(r"[^A-Z0-9]", "", DYD_CANONICAL)

    # Caso exacto o casi exacto:
    # GROUP DYD COMUNICACIONES SAS
    # Group Dyd Comunicaciones Sas
    # GROUP DYD COMUNICACION
    if "GROUP" in normalized and "DYD" in normalized and "COMUNIC" in normalized:
        return True

    if "GRUPO" in normalized and ("DYD" in normalized or "D Y D" in normalized):
        return True

    if ("DYD" in normalized or "D Y D" in normalized) and "COMUNIC" in normalized:
        return True

    # Caso enmascarado:
    # GRO*** DYD***
    # GRO*** DYD*** COM*** SAS***
    # DYD*** COM***
    masked_raw = re.sub(r"\s+", " ", raw)

    has_masked_group = bool(re.search(r"\bGR[O0][A-Z*]*\b", masked_raw))
    has_masked_dyd = bool(
        re.search(r"\bDYD[A-Z*]*\b", masked_raw)
        or re.search(r"\bD\s*\*?\s*Y\s*\*?\s*D[A-Z*]*\b", masked_raw)
    )
    has_masked_com = bool(re.search(r"\bC[O0]M[A-Z*]*\b", masked_raw))
    has_masked_sas = bool(
        re.search(r"\bSAS[A-Z*]*\b", masked_raw)
        or re.search(r"\bS\s*\.?\s*A\s*\.?\s*S[A-Z*]*\b", masked_raw)
    )

    if has_masked_group and has_masked_dyd:
        return True

    if has_masked_dyd and has_masked_com:
        return True

    if has_masked_dyd and has_masked_com and has_masked_sas:
        return True

    # Fuzzy contra nombre completo.
    if _similarity(compact, canonical_compact) >= 0.72:
        return True

    has_dyd = "DYD" in normalized or "D Y D" in normalized
    has_group = "GROUP" in normalized or "GRUPO" in normalized or "GRO" in normalized
    has_comunicaciones = "COMUNIC" in normalized or "COM" in normalized
    has_sas = "SAS" in normalized

    return has_dyd and (has_group or has_comunicaciones or has_sas)


def description_from_text(value: Any) -> str:
    """Devuelve DESCRIPCION según texto OCR/remitente/payload.

    Prioridad:
    1. DAVID GUEVARA => NEQUI
    2. 3176771287 => NEQUI
    3. GROUP DYD COMUNICACIONES SAS o variantes => CUENTA
    4. Sin coincidencias => NINGUNO
    """
    text = _normalize_text(value)

    if not text:
        return NINGUNO_LABEL

    if _contains_david_guevara(text):
        return NEQUI_LABEL

    if _contains_nequi_phone(text):
        return NEQUI_LABEL

    if _contains_dyd_variant(text):
        return CUENTA_LABEL

    return NINGUNO_LABEL


def description_for_deposit_payload(payload: dict[str, Any] | None) -> str:
    """Calcula DESCRIPCION desde el payload estructurado."""
    if not isinstance(payload, dict):
        return NINGUNO_LABEL

    candidates = [
        payload.get("remitente"),
        payload.get("telefono_remitente"),
        payload.get("empresa_origen"),
        payload.get("sender"),
        payload.get("nombre_remitente"),
        payload.get("originador"),
        payload.get("titular"),
        payload.get("cuenta_origen"),
        payload.get("telefono"),
        payload.get("numero_nequi"),
        payload.get("ocr_text"),
        payload.get("raw_text"),
    ]

    combined = " ".join(str(item or "") for item in candidates)
    return description_from_text(combined)


def description_for_deposit(deposit: Any) -> str:
    """Calcula DESCRIPCION usando payload y texto OCR de la imagen fuente."""
    parts: list[str] = []

    payload = getattr(deposit, "structured_payload", None)
    if isinstance(payload, dict):
        parts.append(
            " ".join(
                str(value or "")
                for value in payload.values()
                if isinstance(value, (str, int, float))
            )
        )

    source_image = getattr(deposit, "source_image", None)
    if source_image is not None:
        parts.append(getattr(source_image, "ocr_raw_text", "") or "")
        parts.append(getattr(source_image, "context_text", "") or "")

    return description_from_text(" ".join(parts))
