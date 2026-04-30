# Troubleshooting

## Propósito

Resolver problemas frecuentes del backend usando señales observables en API,
logs y configuración.

## 401 en endpoints protegidos

Revisa:

- header `X-API-Key`;
- variable `API_KEY`;
- `ALLOW_OPEN_API_FOR_DEV`;
- `DJANGO_DEBUG`.

En producción (`DJANGO_DEBUG=0`) `API_KEY` es obligatoria y
`ALLOW_OPEN_API_FOR_DEV` no puede estar activo.

## Error de conexión a base de datos

Revisa:

- `DATABASE_URL`;
- estado del servicio `mariadb` si usas Docker Compose;
- credenciales `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`;
- migraciones con `python manage.py migrate`.

En debug sin `DATABASE_URL`, SQLite es el fallback esperado.

## Fallos al subir DOCX

Validaciones relevantes:

- extensión `.docx`;
- firma ZIP válida;
- límite `DOCX_MAX_UPLOAD_BYTES`;
- máximo `DOCX_MAX_IMAGES`;
- imágenes embebidas reales.

Errores comunes:

| Código | Significado |
| --- | --- |
| `invalid_extension` | El archivo no termina en `.docx` |
| `file_too_large` | Supera el tamaño máximo |
| `invalid_docx` | ZIP/DOCX inválido o corrupto |
| `docx_no_images` | No hay imágenes embebidas procesables |

## Imágenes no extraídas

Verifica que las imágenes estén embebidas en el DOCX y no solo enlazadas o
representadas como texto. Revisa logs `docx_extract_images` y
`source_image_created`.

## OCR devuelve texto vacío

1. Consulta `GET /api/jobs/{id}/logs/` y filtra etapa `ocr`.
2. Revisa `image_validation` para descartar imagen inválida.
3. Confirma `ocr_mode`, `ocr_provider` y `ocr_model`.
4. Revisa `GET /api/processing/provider-health/`.
5. Si usas Tesseract, valida binario e idioma.
6. Si usas Ollama, valida `OLLAMA_URL`, modelo instalado y timeout.

## Resultados peores que antes

Compara:

- `SourceImage.ocr_raw_text`;
- `raw_payload.ocr_raw_text_sample`;
- `raw_payload.score`;
- cantidad de registros estructurados y persistidos;
- `record_skipped`;
- `persistence_mismatch`;
- cambios en preprocesamiento de imágenes.

Si la regresión coincide con preprocesamiento o binarización, consulta
[ocr-troubleshooting.md](ocr-troubleshooting.md).

## Proveedor OCR/LLM no responde

Revisa:

- `OLLAMA_URL`;
- `OLLAMA_TIMEOUT`;
- `request_timeout_seconds`;
- `LLM_MAX_RETRIES`;
- `provider_error_class`;
- `provider_error_message`;
- eventos con `status=timeout`.

`GET /api/processing/provider-health/` reporta modelos instalados, warnings y
si Ollama responde.

## API key inválida

Si el frontend recibe `401`:

1. Confirma que backend y frontend usan la misma clave.
2. En frontend, revisa `VITE_API_KEY`.
3. En backend, revisa `API_KEY`.
4. Si trabajas sin clave local, confirma `ALLOW_OPEN_API_FOR_DEV=1` y
   `DJANGO_DEBUG=1`.

## Diferencias entre proveedores

Tesseract y visión pueden producir textos distintos para la misma imagen. Usa
modo `auto` para comparar intentos y revisa:

- `raw_payload.attempts`;
- `llm_structuring_auto_tesseract`;
- `llm_structuring_auto_vision`;
- `auto_ocr_selected`.

## Problemas por binarización o preprocesamiento

Síntomas típicos:

- dígitos faltantes;
- separadores de fecha/hora/monto perdidos;
- texto fragmentado;
- referencias incompletas;
- montos con escala incorrecta.

El flujo actual no binariza por defecto. Si un cambio activa o modifica
thresholding, ejecuta:

```bash
python manage.py test tests.test_tesseract_ocr
python manage.py test tests.test_ocr_pipeline_stability
```

## Job atascado o con errores parciales

Usa:

```bash
curl -H "X-API-Key: dev" http://localhost:8000/api/jobs/1/processing-state/
curl -H "X-API-Key: dev" http://localhost:8000/api/jobs/1/diagnostics/
curl -H "X-API-Key: dev" http://localhost:8000/api/jobs/1/logs/
```

Si el job quedó con errores parciales:

- `POST /api/jobs/{id}/reprocess-failed/`;
- `POST /api/jobs/{id}/source-images/{source_image_id}/reprocess/`.

## Exportación no disponible

`POST /api/jobs/{id}/export/` solo aplica para:

- `completed`;
- `completed_with_errors`.

Si el job está en `uploaded`, procesa primero. Si está en `failed`, revisa logs
o reprocesa fuentes.

## Enlaces relacionados

- [Configuración](configuration.md)
- [Contrato API](api-contract.md)
- [Pipeline de procesamiento](processing-pipeline.md)
- [Troubleshooting OCR](ocr-troubleshooting.md)
- [Jobs y workers](jobs-and-workers.md)
