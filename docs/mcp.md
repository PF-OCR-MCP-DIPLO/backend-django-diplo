# MCP server for backend-django-diplo

This project includes an MCP server that exposes business tools over the
existing Django services. The HTTP client remains available only as an optional
legacy/fallback adapter for integrations that need to call the REST API.

## Implemented tools

- health_check
- upload_document
- process_job
- get_job_status
- list_jobs
- get_job_logs
- list_job_logs (deprecated alias)
- export_job_excel
- reprocess_failed_sources
- reprocess_source_image
- get_processing_settings
- get_processing_settings_options
- update_processing_settings
- describe_database_schema
- query_database
- query_database_sql
- get_last_record_value
- get_completed_records_summary

## Implemented resources and prompts

Read-only resources:

- `diplo://health`
- `diplo://capabilities`
- `diplo://jobs`
- `diplo://jobs/{job_id}`
- `diplo://jobs/{job_id}/logs`
- `diplo://processing/settings`

Reusable prompts:

- `diagnose_job`
- `explain_results`
- `prepare_reprocessing`

## Environment variables

- No environment variables are required for the default local mode.
- `MCP_ENABLE_MUTATIONS=1` enables mutating tools. When disabled, upload,
  processing, reprocessing, export, corrections, settings updates and CRUD
  mutations return a controlled `403` envelope.
- `MCP_ALLOWED_UPLOAD_ROOTS` optionally restricts `upload_document` to absolute
  `.docx` paths inside one of the configured roots. Multiple roots are separated
  with the OS path separator.
- Legacy HTTP client variables are kept only for optional compatibility/fallback paths:
  - MCP_BACKEND_BASE_URL: backend API base url, default `http://127.0.0.1:8000/api`
  - MCP_BACKEND_API_TOKEN: optional value sent as `X-API-Key`
  - MCP_BACKEND_TIMEOUT: request timeout in seconds, default `60`

## Run

1. Start Django API:

```powershell
python manage.py runserver
```

2. Start MCP server (stdio transport):

```powershell
python -m mcp_server.server
```

## Notes

- `upload_document` requires an absolute path to a `.docx` file.
- `process_job` may take longer than normal API calls; timeout is handled by MCP_BACKEND_TIMEOUT and an internal extended timeout for processing.
- MCP tools execute the same internal business logic used by the multi-agent assistant to keep behavior aligned.
- Tool outputs are JSON strings with a stable envelope:

```json
{
  "ok": true,
  "status_code": null,
  "detail": null,
  "data": {}
}
```

On backend errors:

```json
{
  "ok": false,
  "status_code": 403,
  "detail": "process_job is disabled by server configuration.",
  "data": null,
  "code": "mutation_disabled"
}
```
