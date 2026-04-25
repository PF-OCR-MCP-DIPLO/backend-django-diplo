from __future__ import annotations

TOOL_RISK_LEVELS: dict[str, str] = {
    "health_check": "read_only",
    "describe_database_schema": "read_only",
    "query_database_sql": "restricted",
    "list_jobs": "read_only",
    "get_job_status": "read_only",
    "get_job_logs": "read_only",
    "get_last_record_value": "read_only",
    "get_completed_records_summary": "read_only",
    "query_database": "read_only",
    "crud_database": "requires_confirmation",
    "get_processing_settings": "read_only",
    "get_processing_settings_options": "read_only",
    "update_processing_settings": "requires_confirmation",
    "process_job": "requires_confirmation",
    "export_job_excel": "requires_confirmation",
    "upload_document": "requires_confirmation",
    "list_available_tools": "read_only",
    "explain_capabilities": "read_only",
    "help": "read_only",
}


def get_tool_risk_level(tool: str) -> str:
    return TOOL_RISK_LEVELS.get(tool, "restricted")


def tool_requires_confirmation(tool: str) -> bool:
    return get_tool_risk_level(tool) == "requires_confirmation"

