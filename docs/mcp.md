# MCP server for backend-django-diplo

This project includes an MCP server that exposes business tools over the existing Django REST API.

## Implemented tools

- health_check
- upload_document
- process_job
- get_job_status
- list_jobs
- list_job_logs
- export_job_excel
- get_processing_settings
- get_processing_settings_options
- update_processing_settings

## Environment variables

- MCP_BACKEND_BASE_URL: backend API base url, default `http://127.0.0.1:8000/api`
- MCP_BACKEND_API_TOKEN: optional bearer token
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
- Tool outputs are JSON strings with a stable envelope:

```json
{
  "ok": true,
  "data": {}
}
```

On backend errors:

```json
{
  "ok": false,
  "status_code": 409,
  "detail": "Only completed jobs can be exported.",
  "payload": {"detail": "Only completed jobs can be exported."}
}
```
