"""Diagnóstico y trazabilidad del pipeline de procesamiento."""

from __future__ import annotations

import hashlib
import os
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone
from PIL import Image

from apps.processing.models import ExtractionLog, ProcessRun, SourceImage
from apps.processing.services.ollama_models import get_available_models
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)

MAX_DEBUG_TEXT = 500
STALE_PROCESSING_SECONDS = 300


def real_source_images_queryset(process_run: ProcessRun):
    return process_run.source_images.exclude(
        sequence_index=0,
        source_name="document_text",
    ).exclude(image_file="")


def truncate_debug_text(text: str | None, max_chars: int = MAX_DEBUG_TEXT) -> str:
    """Recorta texto técnico para evitar payloads de diagnóstico excesivos."""
    value = text or ""
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}...[truncated {len(value) - max_chars} chars]"


def get_process_memory_mb() -> float | None:
    try:
        with open("/proc/self/statm", encoding="utf-8") as statm:
            resident_pages = int(statm.read().split()[1])
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((resident_pages * page_size) / (1024 * 1024), 2)
    except Exception:
        return None


def get_image_metadata(source_image: SourceImage | None) -> dict[str, Any]:
    if source_image is None or not source_image.image_file:
        return {}
    metadata: dict[str, Any] = {}
    try:
        metadata["image_bytes"] = source_image.image_file.size
    except Exception:
        pass
    try:
        source_image.image_file.open("rb")
        try:
            with Image.open(source_image.image_file) as image:
                metadata["image_width"] = image.width
                metadata["image_height"] = image.height
                metadata["image_format"] = image.format
        finally:
            source_image.image_file.close()
    except Exception:
        pass
    return metadata


def stable_hash(value: str | bytes | None) -> str:
    if value is None:
        return ""
    binary = value.encode("utf-8", errors="ignore") if isinstance(value, str) else value
    return hashlib.sha256(binary).hexdigest()


def _runtime_value(runtime_config: Any, name: str, default: str = "") -> str:
    return str(getattr(runtime_config, name, default) or default)


def record_processing_event(
    *,
    process_run: ProcessRun,
    source_image: SourceImage | None = None,
    stage: str,
    status: str,
    runtime_config: Any | None = None,
    provider: str = "",
    model: str = "",
    ocr_mode: str = "",
    started_at: timezone.datetime | None = None,
    finished_at: timezone.datetime | None = None,
    duration_ms: int | None = None,
    records_count: int | None = None,
    raw_text: str | None = None,
    raw_text_chars: int | None = None,
    prompt_chars: int | None = None,
    response_chars: int | None = None,
    image_bytes: int | None = None,
    image_width: int | None = None,
    image_height: int | None = None,
    error: BaseException | None = None,
    notes: str = "",
    raw_payload: dict[str, Any] | None = None,
) -> ExtractionLog | None:
    """Persiste un evento técnico de pipeline con metadatos útiles para debug."""
    payload = dict(raw_payload or {})
    now = timezone.now()
    event_started_at = started_at or now
    event_finished_at = (
        finished_at
        if finished_at is not None
        else (now if status != "started" else None)
    )
    sequence_index = source_image.sequence_index if source_image else 0

    if runtime_config is not None:
        provider = provider or _runtime_value(runtime_config, "llm_provider")
        model = model or _runtime_value(runtime_config, "llm_model")
        ocr_mode = ocr_mode or _runtime_value(runtime_config, "ocr_mode")

    if source_image is not None:
        payload.setdefault("source_image_id", source_image.pk)
        payload.setdefault("source_name", source_image.source_name)
        image_meta = get_image_metadata(source_image)
        image_bytes = (
            image_bytes if image_bytes is not None else image_meta.get("image_bytes")
        )
        image_width = (
            image_width if image_width is not None else image_meta.get("image_width")
        )
        image_height = (
            image_height if image_height is not None else image_meta.get("image_height")
        )
        if image_meta.get("image_format"):
            payload.setdefault("image_format", image_meta["image_format"])

    payload.update(
        {
            "job_id": process_run.pk,
            "source_image_id": source_image.pk if source_image else None,
            "sequence_index": sequence_index,
            "stage": stage,
            "status": status,
            "provider": provider,
            "model": model,
            "ocr_mode": ocr_mode,
            "started_at": event_started_at.isoformat() if event_started_at else None,
            "finished_at": event_finished_at.isoformat() if event_finished_at else None,
            "duration_ms": duration_ms,
            "records_count": records_count,
            "raw_text_chars": raw_text_chars,
            "prompt_chars": prompt_chars,
            "response_chars": response_chars,
            "image_bytes": image_bytes,
            "image_width": image_width,
            "image_height": image_height,
            "thread_name": threading.current_thread().name,
            "pid": os.getpid(),
            "memory_rss_mb": get_process_memory_mb(),
        }
    )
    if raw_text is not None:
        payload["raw_text_sha256"] = stable_hash(raw_text)
        payload["raw_text_sample"] = truncate_debug_text(raw_text)
        raw_text_chars = len(raw_text)
        payload["raw_text_chars"] = raw_text_chars
    if error is not None:
        payload["error_class"] = error.__class__.__name__
        payload["error_message"] = truncate_debug_text(str(error), 1000)
        if getattr(settings, "DEBUG", False):
            payload["traceback"] = truncate_debug_text(
                "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
                2000,
            )

    clean_payload = {key: value for key, value in payload.items() if value is not None}
    try:
        return ExtractionLog.objects.create(
            process_run=process_run,
            source_image=source_image,
            sequence_index=sequence_index,
            stage=stage,
            provider=provider,
            model=model,
            ocr_mode=ocr_mode,
            raw_payload=clean_payload,
            raw_text=truncate_debug_text(raw_text or "", 1000) if raw_text else "",
            notes=notes or clean_payload.get("error_message", ""),
            is_error=status in {"failed", "timeout"} or error is not None,
        )
    except Exception:
        return None


def _status_for_error(error: BaseException) -> str:
    if isinstance(error, requests.exceptions.Timeout):
        return "timeout"
    if "timeout" in error.__class__.__name__.lower():
        return "timeout"
    if "timed out" in str(error).lower() or "timeout" in str(error).lower():
        return "timeout"
    return "failed"


@contextmanager
def stage_timer(
    *,
    process_run: ProcessRun,
    source_image: SourceImage | None = None,
    stage: str,
    runtime_config: Any | None = None,
    provider: str = "",
    model: str = "",
    raw_payload: dict[str, Any] | None = None,
):
    """Mide una etapa del pipeline y registra éxito o fallo con contexto."""
    started_monotonic = time.monotonic()
    started_at = timezone.now()
    record_processing_event(
        process_run=process_run,
        source_image=source_image,
        stage=stage,
        status="started",
        runtime_config=runtime_config,
        provider=provider,
        model=model,
        started_at=started_at,
        raw_payload=raw_payload,
    )
    event_payload: dict[str, Any] = {}
    try:
        yield event_payload
    except Exception as error:
        finished_at = timezone.now()
        record_processing_event(
            process_run=process_run,
            source_image=source_image,
            stage=stage,
            status=_status_for_error(error),
            runtime_config=runtime_config,
            provider=provider,
            model=model,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            error=error,
            raw_payload={**(raw_payload or {}), **event_payload},
        )
        raise
    else:
        finished_at = timezone.now()
        record_processing_event(
            process_run=process_run,
            source_image=source_image,
            stage=stage,
            status=event_payload.pop("status", "completed"),
            runtime_config=runtime_config,
            provider=event_payload.pop("provider", provider),
            model=event_payload.pop("model", model),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((time.monotonic() - started_monotonic) * 1000),
            records_count=event_payload.pop("records_count", None),
            raw_text=event_payload.pop("raw_text", None),
            raw_text_chars=event_payload.pop("raw_text_chars", None),
            prompt_chars=event_payload.pop("prompt_chars", None),
            response_chars=event_payload.pop("response_chars", None),
            raw_payload={**(raw_payload or {}), **event_payload},
        )


def _event_payload(log: ExtractionLog) -> dict[str, Any]:
    payload = dict(log.raw_payload or {})
    payload.setdefault("stage", log.stage)
    payload.setdefault("provider", log.provider)
    payload.setdefault("model", log.model)
    payload.setdefault("ocr_mode", log.ocr_mode)
    payload.setdefault("status", "failed" if log.is_error else "completed")
    payload.setdefault(
        "created_at", log.created_at.isoformat() if log.created_at else None
    )
    return payload


def _completed_duration(log: ExtractionLog) -> int:
    payload = log.raw_payload or {}
    if payload.get("status") not in {"completed", "failed", "timeout", "skipped"}:
        return 0
    return int(payload.get("duration_ms") or 0)


def summarize_job_diagnostics(job: ProcessRun) -> dict[str, Any]:
    logs = list(job.extraction_logs.select_related("source_image").order_by("id"))
    events = []
    for log in logs:
        payload = _event_payload(log)
        events.append(
            {
                "id": log.pk,
                "job_id": job.pk,
                "source_image_id": log.source_image_id,
                "sequence_index": log.sequence_index,
                "stage": log.stage,
                "status": payload.get("status"),
                "provider": log.provider,
                "model": log.model,
                "ocr_mode": log.ocr_mode,
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
                "duration_ms": payload.get("duration_ms"),
                "records_count": payload.get("records_count"),
                "raw_text_chars": payload.get("raw_text_chars"),
                "prompt_chars": payload.get("prompt_chars"),
                "response_chars": payload.get("response_chars"),
                "image_bytes": payload.get("image_bytes"),
                "image_width": payload.get("image_width"),
                "image_height": payload.get("image_height"),
                "thread_name": payload.get("thread_name"),
                "pid": payload.get("pid"),
                "memory_rss_mb": payload.get("memory_rss_mb"),
                "error_class": payload.get("error_class"),
                "error_message": payload.get("error_message") or log.notes,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "raw_payload": payload,
            }
        )

    terminal_events = [
        log
        for log in logs
        if (log.raw_payload or {}).get("status") in {"completed", "failed", "timeout"}
    ]
    slowest_log = max(terminal_events, key=_completed_duration, default=None)
    ocr_logs = [
        log
        for log in terminal_events
        if log.stage == "ocr" and (log.raw_payload or {}).get("status") == "completed"
    ]
    llm_logs = [
        log
        for log in terminal_events
        if log.stage == "llm_structuring"
        and (log.raw_payload or {}).get("status") == "completed"
    ]
    failed_images = (
        real_source_images_queryset(job)
        .filter(ocr_status=SourceImage.OCRStatus.FAILED)
        .count()
    )
    total_ocr_duration = sum(_completed_duration(log) for log in ocr_logs)
    total_llm_duration = sum(_completed_duration(log) for log in llm_logs)
    last_log = logs[-1] if logs else None
    stale_processing = False
    if job.status == ProcessRun.Status.PROCESSING:
        reference_time = (
            last_log.created_at if last_log else job.started_at or job.updated_at
        )
        stale_processing = bool(
            reference_time
            and timezone.now() - reference_time
            > timedelta(seconds=STALE_PROCESSING_SECONDS)
        )

    source_images = []
    for image in real_source_images_queryset(job).prefetch_related(
        "deposits", "extraction_logs"
    ):
        image_logs = list(image.extraction_logs.all())
        image_ocr_duration = sum(
            _completed_duration(log)
            for log in image_logs
            if log.stage == "ocr"
            and (log.raw_payload or {}).get("status") == "completed"
        )
        image_llm_duration = sum(
            _completed_duration(log)
            for log in image_logs
            if log.stage == "llm_structuring"
            and (log.raw_payload or {}).get("status") == "completed"
        )
        image_meta = get_image_metadata(image)
        source_images.append(
            {
                "id": image.pk,
                "sequence_index": image.sequence_index,
                "source_name": image.source_name,
                "ocr_status": image.ocr_status,
                "image_file": image.image_file.url if image.image_file else "",
                "image_bytes": image_meta.get("image_bytes"),
                "image_width": image_meta.get("image_width"),
                "image_height": image_meta.get("image_height"),
                "ocr_duration_ms": image_ocr_duration,
                "llm_duration_ms": image_llm_duration,
                "records_count": image.deposits.count(),
                "error_message": image.error_message,
            }
        )

    recommendations = []
    if total_llm_duration > total_ocr_duration * 2 and llm_logs:
        recommendations.append(
            "LLM structuring dominates runtime; test a smaller llm_model or reduce OCR text sent to the LLM."
        )
    if any((item.get("image_bytes") or 0) > 3 * 1024 * 1024 for item in source_images):
        recommendations.append(
            "One or more images are large; resize/compress before OCR or lower EXTRACTED_IMAGE_MAX_BYTES."
        )
    if stale_processing:
        recommendations.append(
            "Job appears stale in processing; inspect worker thread/process and provider timeout logs."
        )
    if failed_images:
        recommendations.append(
            "Some images failed; inspect image_failed and provider timeout events by source_image_id."
        )

    duration_ms = None
    if job.started_at and job.finished_at:
        duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
    elif job.started_at:
        duration_ms = int((timezone.now() - job.started_at).total_seconds() * 1000)

    summary = {
        "ocr_calls": len(ocr_logs),
        "llm_calls": len(llm_logs),
        "failed_images": failed_images,
        "processed_images": real_source_images_queryset(job)
        .filter(ocr_status=SourceImage.OCRStatus.PROCESSED)
        .count(),
        "slowest_stage": slowest_log.stage if slowest_log else None,
        "slowest_source_image_id": slowest_log.source_image_id if slowest_log else None,
        "total_ocr_duration_ms": total_ocr_duration,
        "total_llm_duration_ms": total_llm_duration,
        "avg_ocr_duration_ms": (
            int(total_ocr_duration / len(ocr_logs)) if ocr_logs else 0
        ),
        "avg_llm_duration_ms": (
            int(total_llm_duration / len(llm_logs)) if llm_logs else 0
        ),
        "polling_suspected": False,
        "provider_suspected": bool(
            failed_images
            or total_llm_duration > 30_000
            or total_ocr_duration > 30_000
            or any(event.get("status") == "timeout" for event in events)
        ),
        "stale_processing": stale_processing,
        "last_event_at": last_log.created_at.isoformat() if last_log else None,
    }
    return {
        "job": {
            "id": job.pk,
            "status": job.status,
            "total_images": job.total_images,
            "total_records": job.total_records,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "duration_ms": duration_ms,
            "error_message": job.error_message,
        },
        "summary": summary,
        "events": events,
        "source_images": source_images,
        "recommendations": recommendations,
    }


def summarize_processing_state(job: ProcessRun) -> dict[str, Any]:
    diagnostics = summarize_job_diagnostics(job)
    summary = diagnostics["summary"]
    last_event = diagnostics["events"][-1] if diagnostics["events"] else None
    current_stage = last_event["stage"] if last_event else None
    elapsed_ms = None
    if job.started_at:
        end_time = job.finished_at or timezone.now()
        elapsed_ms = int((end_time - job.started_at).total_seconds() * 1000)
    return {
        "job_id": job.pk,
        "status": job.status,
        "current_stage": current_stage,
        "processed_images": summary["processed_images"],
        "total_images": job.total_images,
        "failed_images": summary["failed_images"],
        "total_records": job.total_records,
        "last_event_at": summary["last_event_at"],
        "elapsed_ms": elapsed_ms,
        "stale_processing": summary["stale_processing"],
    }


def summarize_provider_health() -> dict[str, Any]:
    runtime_config = get_runtime_config()
    snapshot = as_snapshot_dict(runtime_config)
    ollama = get_available_models(timeout=5.0)
    installed = [
        model.get("name")
        for model in ollama.get("models", [])
        if isinstance(model, dict) and model.get("name")
    ]
    model_sizes = {
        model.get("name"): model.get("size")
        for model in ollama.get("models", [])
        if isinstance(model, dict) and model.get("name")
    }
    warnings: list[str] = []
    if (
        runtime_config.ocr_mode in {"vision", "auto"}
        and runtime_config.ocr_model not in installed
    ):
        warnings.append(
            f"OCR model '{runtime_config.ocr_model}' is not installed in Ollama."
        )
    if (
        runtime_config.llm_provider == "ollama"
        and runtime_config.llm_model not in installed
    ):
        warnings.append(
            f"LLM model '{runtime_config.llm_model}' is not installed in Ollama."
        )
    for label, model_name in (
        ("ocr", runtime_config.ocr_model),
        ("llm", runtime_config.llm_model),
    ):
        size = model_sizes.get(model_name)
        if size and size >= 6 * 1024 * 1024 * 1024:
            warnings.append(
                f"{label} model '{model_name}' is large ({round(size / (1024**3), 1)} GiB)."
            )
    if runtime_config.request_timeout_seconds < 15:
        warnings.append("request_timeout_seconds is low for local Ollama workloads.")
    if runtime_config.request_timeout_seconds > 300:
        warnings.append(
            "request_timeout_seconds is high; slow provider calls can occupy workers for minutes."
        )
    return {
        "settings": snapshot,
        "ollama": {
            "url": getattr(settings, "OLLAMA_URL", ""),
            "reachable": bool(ollama.get("available")),
            "models": ollama.get("models", []),
            "error": ollama.get("error"),
        },
        "checks": {
            "ocr_model_exists": (
                runtime_config.ocr_mode == "tesseract"
                or runtime_config.ocr_model in installed
            ),
            "llm_model_exists": runtime_config.llm_model in installed,
            "timeout_seconds": runtime_config.request_timeout_seconds,
        },
        "warnings": warnings,
    }
