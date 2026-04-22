from __future__ import annotations

import json
import os
from typing import Any

import django
from mcp.server.fastmcp import FastMCP

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
django.setup()

from apps.api.services.shared_tools import upload_document_from_path
from apps.api.services.tool_dispatcher import execute_tool
from mcp_server.schemas import JobIdInput, UpdateProcessingSettingsInput, UploadDocumentInput

mcp = FastMCP("backend-django-diplo")


def _as_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def _runtime_error_payload(error: Exception) -> str:
    return _as_json(
        {
            "ok": False,
            "status_code": 500,
            "detail": str(error),
            "payload": None,
        }
    )


def _run_local_tool(tool: str, arguments: dict[str, Any] | None = None, job_id: int | None = None) -> str:
    try:
        payload = execute_tool(tool=tool, arguments=arguments, job_id=job_id)
        return _as_json({"ok": True, "data": payload})
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool()
def health_check() -> str:
    """Check backend service status."""
    return _run_local_tool("health_check")


@mcp.tool()
def upload_document(file_path: str) -> str:
    """Upload a .docx document and create a processing job."""
    try:
        args = UploadDocumentInput(file_path=file_path)
        payload = upload_document_from_path(args.file_path)
        return _as_json({"ok": True, "data": payload})
    except ValueError as error:
        return _as_json({"ok": False, "status_code": 400, "detail": str(error)})
    except Exception as error:  # pragma: no cover - defensive fallback
        return _runtime_error_payload(error)


@mcp.tool()
def process_job(job_id: int) -> str:
    """Run OCR and extraction pipeline for an existing job."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("process_job", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def get_job_status(job_id: int) -> str:
    """Fetch a detailed job status with images and deposits."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("get_job_status", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def list_jobs() -> str:
    """List processing jobs ordered by creation date."""
    return _run_local_tool("list_jobs")


@mcp.tool()
def get_job_logs(job_id: int) -> str:
    """List extraction logs of a processing job."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("get_job_logs", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def list_job_logs(job_id: int) -> str:
    """Deprecated alias for get_job_logs (kept for backward compatibility)."""
    return get_job_logs(job_id)


@mcp.tool()
def export_job_excel(job_id: int) -> str:
    """Generate Excel output for a completed job."""
    args = JobIdInput(job_id=job_id)
    return _run_local_tool("export_job_excel", {"job_id": args.job_id}, job_id=args.job_id)


@mcp.tool()
def get_processing_settings() -> str:
    """Fetch current processing settings."""
    return _run_local_tool("get_processing_settings")


@mcp.tool()
def get_processing_settings_options() -> str:
    """Fetch supported options for processing settings."""
    return _run_local_tool("get_processing_settings_options")


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
    return _run_local_tool("update_processing_settings", args.to_partial_dict())


@mcp.tool()
def describe_database_schema() -> str:
    """Describe allowed sources, fields and query capabilities."""
    return _run_local_tool("describe_database_schema")


@mcp.tool()
def query_database(query: dict[str, Any]) -> str:
    """Execute a safe structured query over allowed data sources."""
    return _run_local_tool("query_database", {"query": query})


@mcp.tool()
def query_database_sql(sql: str, limit: int = 100) -> str:
    """Execute a read-only SQL query when enabled by backend settings."""
    return _run_local_tool("query_database_sql", {"sql": sql, "limit": limit})


@mcp.tool()
def get_last_record_value(job_id: int | None = None) -> str:
    """Get the most recent extracted record value for a job or latest completed job."""
    arguments: dict[str, Any] = {}
    resolved_job_id: int | None = None
    if job_id is not None:
        args = JobIdInput(job_id=job_id)
        arguments["job_id"] = args.job_id
        resolved_job_id = args.job_id
    return _run_local_tool("get_last_record_value", arguments, job_id=resolved_job_id)


@mcp.tool()
def get_completed_records_summary() -> str:
    """Get totals across completed jobs."""
    return _run_local_tool("get_completed_records_summary")


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
