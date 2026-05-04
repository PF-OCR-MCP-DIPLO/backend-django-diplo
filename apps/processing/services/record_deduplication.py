"""Normalización y deduplicación de registros estructurados."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import Iterable

INVISIBLE_SPACES = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\ufeff\u2060"),
    None,
)
MONEY_QUANT = Decimal("0.01")


@dataclass(frozen=True)
class CanonicalRecord:
    key: str
    loose_key: str
    image_fingerprint: str
    fecha: str
    hora: str
    monto: Decimal | None
    referencia: str


def normalize_reference(value) -> str:
    text = str(value or "").translate(INVISIBLE_SPACES).strip().upper()
    return re.sub(r"\s+", " ", text)


def normalize_amount(value) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip()
        if not text:
            return None
        text = re.sub(r"[^\d,.\-]", "", text)
        if not text or text in {"-", ".", ","}:
            return None
        amount = _decimal_from_localized_number(text)
    if amount is None:
        return None
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def normalize_date(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").translate(INVISIBLE_SPACES).strip()
    if not text:
        return ""
    iso_match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso_match:
        return _safe_iso_date(
            int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        )
    local_match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b", text)
    if local_match:
        year = int(local_match.group(3))
        if year < 100:
            year += 2000
        return _safe_iso_date(
            year, int(local_match.group(2)), int(local_match.group(1))
        )
    return re.sub(r"\s+", " ", text).upper()


def normalize_time(value) -> str:
    text = str(value or "").translate(INVISIBLE_SPACES).strip()
    if not text:
        return ""
    match = re.search(r"\b(\d{1,2})[:.hH](\d{2})\b", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    compact = re.search(r"\b(\d{1,2})(\d{2})\b", text)
    if compact:
        hour = int(compact.group(1))
        minute = int(compact.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return re.sub(r"\s+", " ", text).upper()


def canonicalize_record(source_image, record: dict) -> CanonicalRecord:
    image_fingerprint = (
        getattr(source_image, "content_hash", "")
        or f"source:{getattr(source_image, 'pk', '')}"
    )
    referencia = normalize_reference(record.get("referencia"))
    monto = normalize_amount(record.get("valor"))
    fecha = normalize_date(record.get("fecha_consignacion"))
    hora = normalize_time(record.get("hora_consignacion"))
    if not referencia or monto is None:
        return CanonicalRecord(
            "", "", image_fingerprint, fecha, hora, monto, referencia
        )
    parts = [image_fingerprint, fecha, hora, f"{monto:.2f}", referencia]
    loose_parts = [image_fingerprint, f"{monto:.2f}", referencia]
    return CanonicalRecord(
        key="v1:" + sha256("|".join(parts).encode("utf-8")).hexdigest(),
        loose_key="v1:" + sha256("|".join(loose_parts).encode("utf-8")).hexdigest(),
        image_fingerprint=image_fingerprint,
        fecha=fecha,
        hora=hora,
        monto=monto,
        referencia=referencia,
    )


def deduplicate_structured_records(
    *,
    records: Iterable[dict],
    source_image,
    process_run,
    runtime_config,
    log_callback=None,
) -> list[dict]:
    kept: list[dict] = []
    exact_index: dict[str, int] = {}
    loose_index: dict[str, int] = {}
    records_list = list(records or [])

    for index, record in enumerate(records_list, start=1):
        if not isinstance(record, dict):
            kept.append(record)
            continue
        current = dict(record)
        canonical = canonicalize_record(source_image, current)
        if not canonical.key:
            kept.append(current)
            continue

        current["_canonical_key"] = canonical.key
        current["_canonical_fingerprint"] = {
            "image_fingerprint": canonical.image_fingerprint,
            "fecha": canonical.fecha,
            "hora": canonical.hora,
            "valor": f"{canonical.monto:.2f}" if canonical.monto is not None else "",
            "referencia": canonical.referencia,
        }

        duplicate_index = exact_index.get(canonical.key)
        if duplicate_index is not None:
            _log_dedupe(
                log_callback,
                process_run,
                source_image,
                "result_duplicate_skipped",
                runtime_config,
                "Skipped exact duplicate structured result.",
                {
                    "record_index": index,
                    "duplicate_of_index": duplicate_index + 1,
                    "canonical_key": canonical.key,
                    "reason": "same_canonical_transaction_key",
                },
            )
            continue

        candidate_index = loose_index.get(canonical.loose_key)
        if candidate_index is not None:
            previous = kept[candidate_index]
            previous_canonical = canonicalize_record(source_image, previous)
            if _can_merge_by_missing_datetime(previous_canonical, canonical):
                merged = _prefer_more_complete(previous, current)
                merged_canonical = canonicalize_record(source_image, merged)
                merged["_canonical_key"] = merged_canonical.key
                merged["_canonical_fingerprint"] = {
                    "image_fingerprint": merged_canonical.image_fingerprint,
                    "fecha": merged_canonical.fecha,
                    "hora": merged_canonical.hora,
                    "valor": (
                        f"{merged_canonical.monto:.2f}"
                        if merged_canonical.monto is not None
                        else ""
                    ),
                    "referencia": merged_canonical.referencia,
                }
                kept[candidate_index] = merged
                exact_index[merged_canonical.key] = candidate_index
                loose_index[merged_canonical.loose_key] = candidate_index
                _log_dedupe(
                    log_callback,
                    process_run,
                    source_image,
                    "result_candidate_merged",
                    runtime_config,
                    "Merged duplicate candidate with a more complete transaction.",
                    {
                        "record_index": index,
                        "merged_with_index": candidate_index + 1,
                        "canonical_key": merged_canonical.key,
                        "reason": "same_reference_and_amount_with_missing_datetime",
                    },
                )
                continue

        exact_index[canonical.key] = len(kept)
        loose_index.setdefault(canonical.loose_key, len(kept))
        kept.append(current)

    return kept


def _decimal_from_localized_number(text: str) -> Decimal | None:
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    decimal_separator = ""
    if last_comma >= 0 and last_dot >= 0:
        decimal_separator = "," if last_comma > last_dot else "."
    elif last_comma >= 0:
        fraction = text[last_comma + 1 :]
        decimal_separator = "," if len(fraction) in {1, 2} else ""
    elif last_dot >= 0:
        fraction = text[last_dot + 1 :]
        decimal_separator = "." if len(fraction) in {1, 2} else ""

    if decimal_separator:
        thousands_separator = "." if decimal_separator == "," else ","
        normalized = text.replace(thousands_separator, "")
        normalized = normalized.replace(decimal_separator, ".")
    else:
        normalized = text.replace(".", "").replace(",", "")
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _safe_iso_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _completeness_score(record: dict) -> tuple[int, float]:
    canonical = canonicalize_record(None, record)
    filled = sum(
        1
        for value in [
            canonical.fecha,
            canonical.hora,
            canonical.referencia,
            canonical.monto,
        ]
        if value not in ("", None)
    )
    confidence = record.get("confidence") or record.get("confianza") or 0
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    return filled, confidence_value


def _prefer_more_complete(previous: dict, current: dict) -> dict:
    preferred = (
        current
        if _completeness_score(current) > _completeness_score(previous)
        else previous
    )
    other = previous if preferred is current else current
    merged = {**other, **preferred}
    merged["_dedupe_merged_from"] = [
        item
        for item in [
            other.get("_canonical_key"),
            preferred.get("_canonical_key"),
        ]
        if item
    ]
    return merged


def _can_merge_by_missing_datetime(
    left: CanonicalRecord, right: CanonicalRecord
) -> bool:
    if not left.loose_key or left.loose_key != right.loose_key:
        return False
    left_has_datetime = bool(left.fecha and left.hora)
    right_has_datetime = bool(right.fecha and right.hora)
    if left_has_datetime and right_has_datetime:
        return left.fecha == right.fecha and left.hora == right.hora
    return True


def _log_dedupe(
    log_callback,
    process_run,
    source_image,
    stage,
    runtime_config,
    notes,
    raw_payload,
):
    if not log_callback:
        return
    log_callback(
        process_run,
        source_image,
        stage,
        runtime_config,
        notes=notes,
        raw_payload=raw_payload,
    )
