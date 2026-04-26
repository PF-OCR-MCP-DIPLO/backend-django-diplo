# Runbook: fallos de procesamiento

## Cuando falla OCR

- Revisar `processing/provider-health/`.
- Revisar `job logs` y `diagnostics`.
- Confirmar `STUB_PROVIDERS` y `OCR_PROVIDER`.
- Confirmar `TESSERACT_TIMEOUT_SECONDS` si el proveedor es Tesseract.

## Cuando falla LLM

- Revisar `LLM_PROVIDER`, `OLLAMA_URL`, `OLLAMA_MODEL`.
- Confirmar timeouts y conectividad.
- Revisar si `MAX_OCR_CHARS_FOR_LLM` truncó la entrada.

## Cuando falla exportación

- Revisar que el job esté `completed` o `completed_with_errors`.
- Revisar permisos de `MEDIA_ROOT`.
- Revisar logs de `excel_exporter.py`.

## Cuando el job queda en estado incorrecto

- Revisar `processing-state/`.
- Revisar `diagnostics/`.
- Revisar si hubo `job_already_processing`.

## Endpoints útiles

- `GET /api/jobs/<id>/diagnostics/`
- `GET /api/jobs/<id>/processing-state/`
- `GET /api/processing/provider-health/`
