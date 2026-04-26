"""Limpieza de jobs y archivos asociados."""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction

from apps.processing.models import ProcessRun


def _iter_job_files(job: ProcessRun) -> Iterable[tuple[object, str]]:
    if job.source_docx:
        yield job.source_docx.storage, job.source_docx.name
    if job.excel_file:
        yield job.excel_file.storage, job.excel_file.name
    for source_image in job.source_images.all():
        if source_image.image_file:
            yield source_image.image_file.storage, source_image.image_file.name


def _delete_files(file_refs: Iterable[tuple[object, str]]) -> None:
    seen: set[tuple[int, str]] = set()
    for storage, name in file_refs:
        key = (id(storage), name)
        if not name or key in seen:
            continue
        seen.add(key)
        try:
            storage.delete(name)
        except Exception:
            continue


def delete_job_and_files(job: ProcessRun) -> None:
    """Elimina una corrida y programa la limpieza de sus blobs persistidos."""
    file_refs = list(_iter_job_files(job))
    job.delete()
    transaction.on_commit(lambda: _delete_files(file_refs))
