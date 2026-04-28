"""Herramientas compartidas entre la API y el servidor MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.files.base import File

from apps.api.serializers import ProcessRunDetailSerializer
from apps.documents.services.upload_service import create_process_run_from_upload


def upload_document_from_path(file_path: str) -> dict[str, Any]:
    """Sube un DOCX desde disco local usando el mismo flujo de upload de la API.

    Side Effects:
        - Persiste un `ProcessRun` y archivos asociados en storage.
        - Ejecuta las validaciones de upload del dominio (`UploadValidationError`).

    Raises:
        ValueError: Si la ruta no existe o no es `.docx`.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"File not found: {file_path}")
    if path.suffix.lower() != ".docx":
        raise ValueError("Only .docx files are supported")

    with path.open("rb") as file_obj:
        django_file = File(file_obj, name=path.name)
        process_run = create_process_run_from_upload(django_file)

    return ProcessRunDetailSerializer(process_run, context={"request": None}).data
