# Contrato de API

## Propósito

Resumir el contrato HTTP que consume el frontend y que cubren los serializers
actuales. Para detalles de implementación consulta `apps/api/urls.py`,
`apps/api/views.py` y `apps/api/serializers.py`.

## Autenticación

Los endpoints funcionales usan `ApiKeyPermission`. Cuando `API_KEY` tiene valor,
el cliente debe enviar:

```http
X-API-Key: <valor-configurado>
```

En debug, si `API_KEY` está vacío y `ALLOW_OPEN_API_FOR_DEV=1`, la API queda
abierta para desarrollo local.

## Formato de errores

El manejador `api_exception_handler` normaliza errores cuando aplica. Los
clientes deben tolerar:

- sobre estándar `{"error": {"code", "message", "details"}}`;
- `{"detail": "..."}` de DRF;
- errores de validación por campo.

## Endpoints

| Método | Ruta | Entrada | Salida principal |
| --- | --- | --- | --- |
| `GET` | `/api/health/` | N/A | `{"status": "ok"}` |
| `POST` | `/api/documents/upload/` | `multipart/form-data` con `file` `.docx` | `ProcessRunDetail` |
| `GET` | `/api/jobs/` | N/A | Lista `ProcessRunList` |
| `GET` | `/api/jobs/{id}/` | N/A | `ProcessRunDetail` |
| `DELETE` | `/api/jobs/{id}/` | N/A | `204` |
| `POST` | `/api/jobs/{id}/process/` | Query opcional `force=true` | `ProcessRunDetail`, `202` si async |
| `PATCH` | `/api/jobs/{id}/deposits/` | `{ "items": [...] }` | `ProcessRunDetail` |
| `POST` | `/api/jobs/{id}/deposits/{deposit_id}/reprocess/` | N/A | `ProcessRunDetail` |
| `POST` | `/api/jobs/{id}/reprocess-failed/` | N/A | `ProcessRunDetail` |
| `POST` | `/api/jobs/{id}/source-images/{source_image_id}/reprocess/` | N/A | `ProcessRunDetail` |
| `GET` | `/api/jobs/{id}/logs/` | N/A | Lista `ExtractionLog` |
| `GET` | `/api/jobs/{id}/diagnostics/` | N/A | Resumen de diagnóstico |
| `GET` | `/api/jobs/{id}/processing-state/` | N/A | Estado compacto |
| `POST` | `/api/jobs/{id}/export/` | N/A | `ProcessRunDetail` con `excel_file` |
| `GET` | `/api/processing/settings/` | N/A | `ProcessingSettings` |
| `PATCH` | `/api/processing/settings/` | Parcial de settings | `ProcessingSettings` |
| `GET` | `/api/processing/settings/options/` | N/A | Catálogos de opciones |
| `GET` | `/api/processing/ollama/models/` | N/A | Snapshot de modelos |
| `GET` | `/api/processing/provider-health/` | N/A | Salud de proveedores |
| `POST` | `/api/assistant/chat/` | Mensajes y contexto | Respuesta de asistente |

## Objetos principales

### ProcessRunDetail

Campos verificados:

- `id`;
- `original_filename`;
- `status`: `uploaded`, `processing`, `completed`,
  `completed_with_errors`, `failed`;
- `source_docx`;
- `excel_file`;
- `total_images`;
- `total_records`;
- `error_message`;
- `provider_config_snapshot`;
- `started_at`, `finished_at`, `created_at`, `updated_at`;
- `source_images`.

### SourceImage

Campos verificados:

- `id`;
- `sequence_index`;
- `source_name`;
- `content_hash`;
- `ocr_status`: `pending`, `processed`, `failed`;
- `ocr_provider`;
- `ocr_raw_text`;
- `error_message`;
- `image_file`;
- `deposits`;
- `created_at`, `updated_at`.

### ExtractedDeposit

Campos verificados:

- `id`;
- `sequence_index`;
- `fecha_consignacion`;
- `hora_consignacion`;
- `referencia`;
- `valor`;
- `is_current_month`;
- `observations`;
- `structured_payload`;
- `created_at`.

### ProcessingSettings

Campos de lectura/escritura principales:

- `ocr_mode`;
- `ocr_provider`;
- `ocr_model`;
- `llm_provider`;
- `llm_model`;
- `assistant_provider`;
- `assistant_model`;
- `assistant_show_debug_details`;
- `assistant_temperature`;
- `assistant_num_predict`;
- `request_timeout_seconds`;
- `valid_consignation_month`;
- `valid_consignation_year`;
- `extraction_criteria`.

Las API keys (`ocr_api_key`, `llm_api_key`, `assistant_api_key`) son
write-only. La lectura expone `has_ocr_api_key`, `has_llm_api_key` y
`has_assistant_api_key`.

## Payload de correcciones manuales

```json
{
  "items": [
    {
      "id": 1,
      "fecha_consignacion": "15/04/2026",
      "hora_consignacion": "09:30",
      "referencia": "REF001",
      "valor": "50000.00"
    }
  ]
}
```

Cada `id` debe pertenecer a un depósito de la corrida. El backend rechaza
correcciones mientras el job está en `processing`.

## Diagnóstico

`/api/jobs/{id}/diagnostics/` devuelve:

- `job`;
- `summary`;
- `events`;
- `source_images`;
- `recommendations`.

`summary` incluye conteos OCR/LLM, imágenes fallidas, etapa más lenta,
duraciones promedio, sospecha de proveedor y estado stale.

## Códigos de estado relevantes

| Código | Caso |
| --- | --- |
| `200` | Lectura o procesamiento síncrono completado |
| `201` | DOCX subido y corrida creada |
| `202` | Procesamiento iniciado en background |
| `204` | Borrado exitoso |
| `400` | Payload inválido, DOCX inválido o fuente no reprocesable |
| `401` | API key faltante o inválida |
| `404` | Recurso inexistente |
| `409` | Conflicto de estado, por ejemplo job en procesamiento |

## Compatibilidad con frontend

El frontend normaliza este contrato en:

- `src/services/http/client.ts`;
- `src/features/processing/api/processing.api.ts`;
- `src/features/settings/api/settings.api.ts`;
- `src/features/assistant/api/assistant.api.ts`.

Si se agrega, elimina o renombra un campo de API, actualiza serializers, docs y
tests de ambos repositorios.
