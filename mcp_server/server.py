from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.api_client import BackendApiClient, BackendApiError
from mcp_server.schemas import JobIdInput, UpdateProcessingSettingsInput, UploadDocumentInput

mcp = FastMCP("backend-django-diplo")
client = BackendApiClient()


def _as_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def _error_payload(error: BackendApiError) -> str:
    return _as_json(
        {
            "ok": False,
            "status_code": error.status_code,
            "detail": error.detail,
            "payload": error.payload,
        }
    )


@mcp.tool()
def health_check() -> str:
    """Check backend API availability."""
    try:
        payload = client.get_health()
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def upload_document(file_path: str) -> str:
    """Upload a .docx document and create a processing job."""
    try:
        args = UploadDocumentInput(file_path=file_path)
        payload = client.upload_document(args.file_path)
        return _as_json({"ok": True, "data": payload})
    except (ValueError, BackendApiError) as error:
        if isinstance(error, BackendApiError):
            return _error_payload(error)
        return _as_json({"ok": False, "status_code": 400, "detail": str(error)})


@mcp.tool()
def process_job(job_id: int) -> str:
    """Run OCR and extraction pipeline for an existing job."""
    try:
        args = JobIdInput(job_id=job_id)
        payload = client.process_job(args.job_id)
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def get_job_status(job_id: int) -> str:
    """Fetch a detailed job status with images and deposits."""
    try:
        args = JobIdInput(job_id=job_id)
        payload = client.get_job_status(args.job_id)
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def list_jobs() -> str:
    """List processing jobs ordered by creation date."""
    try:
        payload = client.list_jobs()
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def list_job_logs(job_id: int) -> str:
    """List extraction logs of a processing job."""
    try:
        args = JobIdInput(job_id=job_id)
        payload = client.get_job_logs(args.job_id)
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def export_job_excel(job_id: int) -> str:
    """Generate Excel output for a completed job."""
    try:
        args = JobIdInput(job_id=job_id)
        payload = client.export_job_excel(args.job_id)
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def get_processing_settings() -> str:
    """Fetch current processing settings."""
    try:
        payload = client.get_processing_settings()
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def get_processing_settings_options() -> str:
    """Fetch supported options for processing settings."""
    try:
        payload = client.get_processing_settings_options()
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


@mcp.tool()
def update_processing_settings(
    ocr_mode: str | None = None,
    ocr_provider: str | None = None,
    ocr_model: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    ocr_api_key: str | None = None,
    llm_api_key: str | None = None,
    request_timeout_seconds: int | None = None,
) -> str:
    """Patch processing settings with partial updates."""
    try:
        args = UpdateProcessingSettingsInput(
            ocr_mode=ocr_mode,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            llm_provider=llm_provider,
            llm_model=llm_model,
            ocr_api_key=ocr_api_key,
            llm_api_key=llm_api_key,
            request_timeout_seconds=request_timeout_seconds,
        )
        payload = client.update_processing_settings(args.to_partial_dict())
        return _as_json({"ok": True, "data": payload})
    except BackendApiError as error:
        return _error_payload(error)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
