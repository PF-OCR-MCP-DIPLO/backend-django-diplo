# Troubleshooting OCR y binarización

## Propósito

Guiar el diagnóstico de problemas de OCR, especialmente regresiones causadas por
preprocesamiento de imágenes o binarización.

## Qué es la binarización

En OCR, binarizar significa convertir una imagen a blanco y negro usando un
umbral. En este proyecto la función `preprocess_image_for_ocr` acepta
`binarize`, pero el flujo actual no lo activa por defecto:

- Tesseract llama a `preprocess_image_for_ocr(source_image.image_file)` sin
  binarizar.
- Visión llama a `preprocess_image_for_ocr(..., binarize=False, sharpen=True)`.

La decisión es intencional: algunos comprobantes tienen texto de tono medio,
sombras o antialiasing. Un umbral fijo puede borrar caracteres que todavía eran
legibles para OCR.

## Cuándo puede ayudar

La binarización puede mejorar resultados si:

- el texto es oscuro y el fondo es muy claro;
- hay poco ruido;
- los bordes de los caracteres son gruesos;
- el proveedor OCR confunde grises de fondo con contenido.

## Cuándo puede empeorar

Puede degradar el OCR si:

- el texto es gris, delgado o de bajo contraste;
- el comprobante viene de una captura comprimida;
- hay sombras, fondos de color o gradientes;
- los separadores de fecha, hora o monto son finos;
- el umbral convierte dígitos parcialmente visibles en blanco.

## Síntomas de mala binarización

| Síntoma | Ejemplo de impacto |
| --- | --- |
| Pérdida de dígitos | Referencia `M06182308` queda como `M0618230` |
| Pérdida de separadores | `03/03/2026` queda como `03032026` |
| Texto fragmentado | Palabras cortadas o líneas partidas |
| Referencias incompletas | Número de comprobante truncado |
| Montos mal interpretados | `$20.000,00` leído como `2000` o `20.00` |
| Fechas/hora dañadas | `09:30` leído como `0930` o `0:30` |

## Señales que deben revisarse

En una corrida real, compara:

- `SourceImage.ocr_raw_text`;
- `ExtractionLog.raw_text`;
- `raw_payload.ocr_raw_text_sample`;
- `raw_payload.raw_text_chars`;
- `raw_payload.score`;
- `raw_payload.attempts` en modo `auto`;
- `raw_payload.selected_engine` en `auto_ocr_selected`;
- `structured_records_count`;
- `persisted_records_count`;
- `record_skipped` y `persistence_mismatch`.

## Diagnóstico rápido por endpoint

```bash
curl -H "X-API-Key: dev" http://localhost:8000/api/jobs/1/logs/
curl -H "X-API-Key: dev" http://localhost:8000/api/jobs/1/diagnostics/
curl -H "X-API-Key: dev" http://localhost:8000/api/processing/provider-health/
```

Ajusta el valor de `X-API-Key` según tu `.env`. Si `ALLOW_OPEN_API_FOR_DEV=1` y
`API_KEY` está vacío, el header no es necesario en debug.

## Casos frecuentes

### OCR devuelve texto vacío

1. Verifica que la imagen existe en `source_images` y tiene `image_file`.
2. Revisa `image_validation` para detectar imagen corrupta o formato no soportado.
3. Consulta `provider-health` para confirmar modelo Ollama instalado.
4. Si usas Tesseract, confirma el binario y el idioma `spa`.
5. Revisa timeouts: `TESSERACT_TIMEOUT_SECONDS`, `OLLAMA_TIMEOUT` y
   `request_timeout_seconds`.

### Resultados peores que antes

1. Compara `ocr_raw_text_sample` entre la versión anterior y la actual.
2. Busca cambios en `apps/extraction/providers/ocr/tesseract.py` y
   `apps/extraction/services/ocr_service.py`.
3. Ejecuta los tests de regresión OCR.
4. Si cambió preprocesamiento, prueba con una imagen de tono medio y una de alto
   contraste.
5. Revisa si el modo cambió de `vision` a `tesseract` o `auto`.

### Diferencias entre proveedores

Tesseract y modelos de visión no leen igual. Usa modo `auto` cuando necesites
comparar:

- `attempts` muestra texto y score por motor;
- `llm_structuring_auto_tesseract` y `llm_structuring_auto_vision` muestran
  resultados estructurados por candidato;
- `auto_ocr_selected` explica la selección final.

### Proveedor no responde

Revisa:

- `OLLAMA_URL`;
- disponibilidad de Ollama;
- modelo instalado;
- `provider_error_class`;
- `provider_error_message`;
- `duration_ms` y eventos con `status=timeout`.

### DOCX sin imágenes

El backend solo procesa imágenes embebidas. Si el documento contiene texto
normal de Word pero no imágenes, el upload falla con `docx_no_images`.

## Tests mínimos antes de aceptar cambios OCR

```bash
python manage.py test tests.test_tesseract_ocr
python manage.py test tests.test_ocr_pipeline_stability
python manage.py test tests.test_processing_diagnostics
python manage.py test tests.test_extraction_providers
```

La prueba
`test_tesseract_runner_preserves_midtone_receipt_text` protege la regresión de
texto de tono medio que puede desaparecer al binarizar.

## Evidencia recomendada en un reporte de regresión

Incluye:

- commit bueno y commit malo;
- `ocr_mode`, `ocr_provider`, `ocr_model`, `llm_model`;
- imagen afectada o `source_image_id`;
- `ocr_raw_text` anterior y actual;
- extracto de `/logs/` para etapas `ocr` y `llm_structuring`;
- extracto de `/diagnostics/`;
- cantidad de registros estructurados y persistidos;
- si el problema afecta fechas, horas, referencias o montos.

## Investigación con Git

```bash
git log --oneline -- apps/extraction apps/processing tests
git diff <commit-bueno>..<commit-malo> -- apps/extraction apps/processing tests
git blame apps/extraction/providers/ocr/tesseract.py
```

Si la regresión no es evidente:

```bash
git bisect start
git bisect bad
git bisect good <commit-bueno>
python manage.py test tests.test_tesseract_ocr tests.test_ocr_pipeline_stability
```

Marca cada paso con `git bisect good` o `git bisect bad` según el resultado del
comando reproducible.
