"""Arranque síncrono o asíncrono de corridas de procesamiento."""

from __future__ import annotations

import logging
import threading

from django.db import close_old_connections

from apps.processing.models import ProcessRun
from apps.processing.services.orchestrator import (
    mark_job_failed,
    prepare_job_for_processing,
    process_prepared_job,
)

logger = logging.getLogger(__name__)

_running_jobs: set[int] = set()
_running_jobs_lock = threading.Lock()


def start_job_processing(process_run: ProcessRun, *, force: bool = False) -> ProcessRun:
    """Prepara y lanza una corrida en segundo plano si la configuración lo permite."""
    process_run = ProcessRun.objects.get(pk=process_run.pk)
    if process_run.status == ProcessRun.Status.PROCESSING:
        raise RuntimeError("job_already_processing")
    if process_run.status == ProcessRun.Status.COMPLETED and not force:
        return process_run

    with _running_jobs_lock:
        if process_run.pk in _running_jobs:
            raise RuntimeError("job_already_processing")
        _running_jobs.add(process_run.pk)

    runtime_config = None
    try:
        prepared_job, runtime_config = prepare_job_for_processing(process_run)
    except Exception as error:
        mark_job_failed(process_run.pk, error, runtime_config)
        with _running_jobs_lock:
            _running_jobs.discard(process_run.pk)
        raise

    worker = threading.Thread(
        target=_run_job_in_background,
        args=(prepared_job.pk, runtime_config, threading.get_ident()),
        daemon=True,
        name=f"process-job-{prepared_job.pk}",
    )
    worker.start()
    return prepared_job


def _run_job_in_background(job_id, runtime_config, parent_thread_id=None):
    """Ejecuta el pipeline en un hilo aislado y limpia el registro de corrida."""
    running_in_worker_thread = parent_thread_id != threading.get_ident()
    if running_in_worker_thread:
        close_old_connections()
    try:
        process_run = ProcessRun.objects.get(pk=job_id)
        process_prepared_job(process_run, runtime_config)
    except Exception as error:
        logger.exception("Background processing failed for job %s", job_id)
        mark_job_failed(job_id, error, runtime_config)
    finally:
        with _running_jobs_lock:
            _running_jobs.discard(job_id)
        if running_in_worker_thread:
            close_old_connections()
