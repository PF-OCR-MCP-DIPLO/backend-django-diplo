# Arquitectura Backend

## Mapa de módulos

- `MCP_back.settings`: configuración de entorno, seguridad, CORS, API key, OCR/LLM y límites.
- `MCP_back.urls`: root views, documentación OpenAPI y montaje de la API.
- `apps/api`: capa REST pública.
- `apps/processing`: persistencia y servicios de orquestación.
- `apps/extraction`: proveedores OCR/LLM, validaciones y schemas.
- `apps/documents`: ingestión del DOCX y creación de corridas.
- `mcp_server`: cliente y servidor para interoperabilidad MCP.

## Flujo de datos

1. `documents/upload/` crea un `ProcessRun` y las fuentes derivadas.
2. `jobs/:id/process/` delega en el orquestador y el runner.
3. Los proveedores OCR/LLM producen texto y estructura.
4. `processing/services/*` consolida depósitos, logs, diagnósticos y exportación.
5. El frontend consume `jobs/:id/`, `jobs/:id/logs/`, `jobs/:id/export/` y settings.

## Endpoints principales

- `GET /api/health/`
- `POST /api/documents/upload/`
- `GET /api/jobs/`
- `GET /api/jobs/<id>/`
- `POST /api/jobs/<id>/process/`
- `POST /api/jobs/<id>/reprocess-failed/`
- `POST /api/jobs/<id>/export/`
- `PATCH /api/jobs/<id>/deposits/`
- `GET /api/processing/settings/`
- `POST /api/assistant/chat/`

## Riesgos o puntos sensibles

- La API key puede ser opcional en desarrollo, pero obligatoria en producción.
- El backend mezcla modo async/sync según `PROCESS_JOBS_ASYNC`.
- Los proveedores reales dependen de red, tiempo de respuesta y configuración externa.
- Los archivos generados viven en `MEDIA_ROOT` y deben considerarse parte del estado del sistema.

