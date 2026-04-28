# Troubleshooting

## Propósito

Resolver problemas comunes del backend con señales observables en código y endpoints.

## 401 en endpoints protegidos

- Verifica header `X-API-Key`.
- Revisa `API_KEY` y `ALLOW_OPEN_API_FOR_DEV`.
- Confirma si `api_key_required()` aplica en tu entorno (`apps/api/auth.py`).

## Error de conexión a base de datos

- Valida `DATABASE_URL`.
- Si usas MariaDB con Docker, comprueba que el servicio `mariadb` está saludable.
- En debug sin `DATABASE_URL`, confirma que SQLite local sea aceptable para tu flujo.

## Fallos al subir DOCX

- Verifica que el archivo termine en `.docx`.
- Revisa firma ZIP y límites (`DOCX_MAX_UPLOAD_BYTES`).
- Consulta respuesta de error de `DocumentUploadView` para código de validación.

## Job atascado o con errores parciales

- Consulta `GET /api/jobs/{id}/processing-state/`.
- Revisa logs de extracción con `GET /api/jobs/{id}/logs/`.
- Usa `POST /api/jobs/{id}/reprocess-failed/` o reproceso por imagen.

## OCR/LLM no responde

- Confirma modelos y timeouts en settings (`OLLAMA_*`, `TESSERACT_TIMEOUT_SECONDS`).
- Si necesitas determinismo en demos/tests, activa `STUB_PROVIDERS=1`.
- Revisa `GET /api/processing/provider-health/`.

## Exportación no disponible

- `POST /api/jobs/{id}/export/` solo aplica para estados `completed` o
  `completed_with_errors`.
- Si el job está en `processing` o `failed`, procesa/reprocesa antes de exportar.

## Enlaces relacionados

- [Configuración](configuration.md)
- [API](api.md)
- [Jobs y workers](jobs-and-workers.md)

