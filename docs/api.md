# API del backend

## Propósito

Documentar rutas REST reales según `apps/api/urls.py` y `apps/api/views.py`.

## Esquema OpenAPI

- `GET /api/schema/`
- `GET /api/docs/` (Swagger UI)
- `GET /api/redoc/`

## Endpoints principales

- `GET /api/health/`: health check.
- `POST /api/documents/upload/`: crea corrida desde DOCX.
- `GET /api/jobs/`: lista corridas.
- `GET /api/jobs/{id}/`: detalle de corrida.
- `DELETE /api/jobs/{id}/`: elimina corrida (si no está en procesamiento).
- `POST /api/jobs/{id}/process/`: inicia/reinicia procesamiento (`force` opcional).
- `POST /api/jobs/{id}/reprocess-failed/`: reproceso de fuentes fallidas.
- `POST /api/jobs/{id}/source-images/{source_image_id}/reprocess/`: reproceso puntual.
- `POST /api/jobs/{id}/deposits/{deposit_id}/reprocess/`: reproceso por consignación.
- `PATCH /api/jobs/{id}/deposits/`: correcciones manuales en lote.
- `GET /api/jobs/{id}/logs/`: logs de extracción.
- `GET /api/jobs/{id}/diagnostics/`: diagnóstico técnico.
- `GET /api/jobs/{id}/processing-state/`: estado operativo resumido.
- `POST /api/jobs/{id}/export/`: exportación Excel.
- `GET/PATCH /api/processing/settings/`: lectura/actualización de configuración singleton.
- `GET /api/processing/settings/options/`: catálogos de opciones.
- `GET /api/processing/ollama/models/`: snapshot de modelos Ollama.
- `GET /api/processing/provider-health/`: salud de proveedores.
- `POST /api/assistant/chat/`: chat de asistente contextual.

## Contratos de autenticación

La mayoría de endpoints usa `ApiKeyPermission`. Ver detalle en [authentication.md](authentication.md).

## Errores esperables

- `400`: payload inválido o recurso no reprocesable.
- `401`: API key faltante/inválida.
- `404`: recurso no encontrado.
- `409`: conflicto de estado (p. ej., job en `processing`).

## Pendiente de validar

- Si existen consumidores externos adicionales al frontend local que dependan de
  campos no cubiertos por tests actuales.

## Enlaces relacionados

- [Autenticación](authentication.md)
- [Jobs y workers](jobs-and-workers.md)
- [Testing](testing.md)
