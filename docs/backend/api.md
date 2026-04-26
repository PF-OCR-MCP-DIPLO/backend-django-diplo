# API REST

La API está expuesta bajo `/api/` y usa `drf-spectacular` para schema y
documentación interactiva.

## OpenAPI

- Schema JSON: `GET /api/schema/`
- Swagger UI: `GET /api/docs/`
- ReDoc: `GET /api/redoc/`

Comando de generación local:

```bash
python manage.py spectacular --file openapi.yaml
```

Pendiente de confirmar: este comando depende del entorno Django con las
dependencias instaladas y genera un archivo local que no debe versionarse salvo
que el equipo decida publicarlo como artefacto.

## Contratos principales

| Método | Ruta | Vista | Propósito | Auth | Entrada | Salida | Errores |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/api/health/` | `HealthView` | Health check | No | N/A | `{status: ok}` | Bajo |
| `POST` | `/api/documents/upload/` | `DocumentUploadView` | Crear corrida desde DOCX | `X-API-Key` | Multipart con `file` | `ProcessRunDetailSerializer` | 400, 401 |
| `GET` | `/api/jobs/` | `JobListView` | Listar corridas | `X-API-Key` | N/A | `ProcessRunListSerializer[]` | 401 |
| `GET` | `/api/jobs/<id>/` | `JobDetailView` | Ver detalle de corrida | `X-API-Key` | N/A | `ProcessRunDetailSerializer` | 401, 404 |
| `DELETE` | `/api/jobs/<id>/` | `JobDetailView` | Borrar corrida | `X-API-Key` | N/A | 204 | 401, 404, 409 |
| `POST` | `/api/jobs/<id>/process/` | `JobProcessView` | Procesar o reprocesar corrida | `X-API-Key` | Query `force` opcional | `ProcessRunDetailSerializer` | 401, 409 |
| `POST` | `/api/jobs/<id>/reprocess-failed/` | `JobReprocessFailedView` | Reprocesar fuentes fallidas | `X-API-Key` | N/A | `ProcessRunDetailSerializer` | 401, 409 |
| `POST` | `/api/jobs/<id>/source-images/<source_image_id>/reprocess/` | `JobSourceImageReprocessView` | Reprocesar una imagen fuente | `X-API-Key` | N/A | `ProcessRunDetailSerializer` | 401, 404, 409, 400 |
| `POST` | `/api/jobs/<id>/deposits/<deposit_id>/reprocess/` | `JobDepositReprocessView` | Reprocesar una consignación | `X-API-Key` | N/A | `ProcessRunDetailSerializer` | 401, 404, 409 |
| `PATCH` | `/api/jobs/<id>/deposits/` | `JobDepositsBulkUpdateView` | Corregir depósitos manualmente | `X-API-Key` | `BulkDepositCorrectionSerializer` | `ProcessRunDetailSerializer` | 401, 400, 409 |
| `GET` | `/api/jobs/<id>/logs/` | `JobLogsView` | Leer logs de extracción | `X-API-Key` | N/A | `ExtractionLogSerializer[]` | 401, 404 |
| `GET` | `/api/jobs/<id>/diagnostics/` | `JobDiagnosticsView` | Diagnóstico de corrida | `X-API-Key` | N/A | Resumen de diagnóstico | 401, 404 |
| `GET` | `/api/jobs/<id>/processing-state/` | `JobProcessingStateView` | Resumen operativo de corrida | `X-API-Key` | N/A | Resumen de estado | 401, 404 |
| `POST` | `/api/jobs/<id>/export/` | `JobExportView` | Generar/registrar exportación Excel | `X-API-Key` | N/A | `ProcessRunDetailSerializer` | 401, 404, 409 |
| `GET` | `/api/processing/settings/` | `ProcessingSettingsView` | Leer settings singleton | `X-API-Key` | N/A | `ProcessingSettingsSerializer` | 401 |
| `PATCH` | `/api/processing/settings/` | `ProcessingSettingsView` | Actualizar settings singleton | `X-API-Key` | Parcial JSON | `ProcessingSettingsSerializer` | 401, 400 |
| `GET` | `/api/processing/settings/options/` | `ProcessingSettingsOptionsView` | Opciones de formulario | `X-API-Key` | N/A | JSON de opciones | 401 |
| `GET` | `/api/processing/ollama/models/` | `OllamaModelsView` | Snapshot de modelos Ollama | `X-API-Key` | N/A | JSON de modelos | 401 |
| `GET` | `/api/processing/provider-health/` | `ProviderHealthView` | Estado de proveedores | `X-API-Key` | N/A | Resumen de salud | 401 |
| `POST` | `/api/assistant/chat/` | `AssistantChatView` | Chat contextual del asistente | `X-API-Key` | `AssistantChatSerializer` | Respuesta de chat | 401, 400 |

## Contratos inferidos por uso

- `BulkDepositCorrectionSerializer` espera un payload con `items`.
- `AssistantChatSerializer` recibe un historial de mensajes, `job_id`, `errors`
  y `query_context`.
- `ProcessRunDetailSerializer` incluye `source_images` con `deposits`, rutas de
  archivos y metadatos de estado.

## Riesgos documentales

- Los detalles exactos de `BulkDepositCorrectionSerializer` y
  `AssistantChatSerializer` deben verificarse en tests si cambian los campos.
- La API no expone usuarios ni sesiones; la autenticación real es por `X-API-Key`.
