# Pipeline de procesamiento

## Propósito

Documentar el flujo real de procesamiento de DOCX a consignaciones exportables,
incluyendo las etapas donde se producen logs y los puntos sensibles para OCR.

## Vista general

```mermaid
flowchart LR
    A[Upload DOCX] --> B[Extraer imagenes y texto]
    B --> C[Validar imagen]
    C --> D[Preprocesar para OCR]
    D --> E[OCR]
    E --> F[Limpieza de texto]
    F --> G[Estructuracion LLM]
    G --> H[Validacion]
    H --> I[Persistencia]
    I --> J[Correcciones manuales]
    J --> K[Exportacion Excel]
    I --> L[Diagnosticos]
```

## Etapas verificadas

| Etapa | Código principal | Salida observable |
| --- | --- | --- |
| Carga | `DocumentUploadView`, `create_process_run_from_upload` | `ProcessRun` en estado `uploaded` |
| Extracción DOCX | `extract_images_in_order`, `extract_text_from_docx` | `SourceImage`, `ProcessRun.extracted_text` |
| Validación de imagen | `validate_source_image` | Evento `image_validation` |
| Preprocesamiento | `preprocess_image_for_ocr` | Archivo temporal PNG usado por OCR |
| OCR | `extract_raw_text` | Evento `ocr`, `ocr_raw_text`, intentos y score |
| Limpieza | `CleaningAgent` | Texto limpio para estructuración |
| Estructuración | `extract_structured_data` | Evento `llm_structuring`, registros candidatos |
| Validación | `ValidationAgent`, `build_record_observations` | `validation_passed`, `validation_failed` |
| Persistencia | `ValidationPersistenceAgent` | `ExtractedDeposit`, `persistence_summary` |
| Reproceso | `reprocess_source_image`, `reprocess_failed_sources` | Nuevos logs por fuente |
| Exportación | `export_job_to_excel` | `ProcessRun.excel_file` |
| Diagnóstico | `summarize_job_diagnostics` | `/api/jobs/{id}/diagnostics/` |

## 1. Carga de DOCX

La API recibe `multipart/form-data` con el campo `file`. La validación rechaza:

- extensiones distintas de `.docx`;
- archivos que superan `DOCX_MAX_UPLOAD_BYTES`;
- contenedores ZIP inválidos o corruptos;
- DOCX sin imágenes embebidas procesables.

La carga crea una corrida y toma un snapshot de configuración con
`get_runtime_config()`.

## 2. Extracción de imágenes

`extract_images_in_order` abre el paquete OpenXML y recorre `word/document.xml`
para resolver relaciones de imágenes. El orden visual se mantiene mediante
`sequence_index`.

Límites relevantes:

- `DOCX_MAX_IMAGES`;
- `EXTRACTED_IMAGE_MAX_BYTES`;
- firmas de imagen soportadas en `image_validation.py`: PNG, JPEG, GIF, BMP y
  WebP.

## 3. Validación y preprocesamiento

Antes de OCR se valida que la imagen no esté vacía, no exceda el tamaño máximo y
tenga una firma compatible. Después, `preprocess_image_for_ocr` prepara un PNG
temporal:

- corrige orientación EXIF;
- convierte a escala de grises;
- aplica autocontraste;
- duplica tamaño si el lado menor es inferior a 1000 px;
- puede aplicar sharpen en modo visión;
- acepta `binarize`, pero el flujo actual lo deja en `False`.

La binarización no debe activarse de forma global sin pruebas de regresión,
porque un umbral fijo puede borrar tonos medios en comprobantes escaneados o
capturas de baja calidad.

## 4. OCR

`extract_raw_text` soporta tres modos:

| Modo | Comportamiento |
| --- | --- |
| `tesseract` | Ejecuta Tesseract local con idioma resuelto desde `ocr_model` |
| `vision` | Envía imagen preprocesada al proveedor de visión, hoy Ollama o stub |
| `auto` | Ejecuta Tesseract y visión, compara score y registros estructurados |

El resultado seleccionado conserva:

- `text`;
- `provider`;
- `model`;
- `mode`;
- `score`;
- `attempts`;
- `fallback_used`;
- muestras y tamaños de texto OCR.

## 5. Limpieza y estructuración

La limpieza de texto ocurre antes de enviar el OCR al LLM. La estructuración usa
`extract_structured_data` con:

- proveedor `ollama` o stub;
- `llm_model`;
- `request_timeout_seconds`;
- `LLM_MAX_RETRIES`;
- `MAX_OCR_CHARS_FOR_LLM`;
- `extraction_criteria`.

Si el LLM no devuelve registros, se intenta un fallback heurístico conservador
que exige al menos valor monetario y referencia plausible.

## 6. Validación y persistencia

La persistencia exige `referencia` y `valor`. Los registros inválidos generan
`record_skipped`. Si hubo registros estructurados pero no se persistió ninguno,
se registra `persistence_mismatch` y la imagen queda como fallida.

Las observaciones incluyen:

- fecha faltante o inválida;
- fecha fuera del periodo configurado;
- reglas de `extraction_criteria`;
- marca de fallback heurístico cuando aplique.

## 7. Reprocesamiento

El backend permite:

- reprocesar todas las fuentes fallidas con
  `POST /api/jobs/{id}/reprocess-failed/`;
- reprocesar una imagen con
  `POST /api/jobs/{id}/source-images/{source_image_id}/reprocess/`;
- reprocesar desde un depósito con
  `POST /api/jobs/{id}/deposits/{deposit_id}/reprocess/`.

El reproceso borra depósitos/logs de la fuente afectada, conserva la corrida y
recalcula estado y contadores.

## 8. Exportación

`POST /api/jobs/{id}/export/` solo acepta corridas en `completed` o
`completed_with_errors`. El Excel contiene las columnas definidas en
`apps/processing/services/excel_exporter.py`.

## Diagnóstico de pipeline

Usa estos endpoints durante investigación:

| Endpoint | Uso |
| --- | --- |
| `GET /api/jobs/{id}/logs/` | Eventos técnicos crudos |
| `GET /api/jobs/{id}/diagnostics/` | Resumen, eventos, imágenes y recomendaciones |
| `GET /api/jobs/{id}/processing-state/` | Estado compacto para polling |
| `GET /api/processing/provider-health/` | Modelos Ollama y warnings de configuración |

Campos clave:

- `stage`;
- `status`;
- `provider`;
- `model`;
- `ocr_mode`;
- `raw_text_chars`;
- `ocr_raw_text_sample`;
- `image_width`, `image_height`, `image_bytes`;
- `provider_error_class`;
- `provider_error_message`;
- `attempts`.

## Validación de cambios futuros

Antes de cambiar OCR, preprocesamiento o estructuración:

```bash
python manage.py test tests.test_tesseract_ocr
python manage.py test tests.test_ocr_pipeline_stability
python manage.py test tests.test_processing_diagnostics
python manage.py test tests.test_extraction_providers
python manage.py test tests.test_docx_extractor
```

Para comparar comportamiento con una muestra controlada:

```bash
python scripts/debug_processing_pipeline.py --stub --sync --max-images 1
```

Con OCR/LLM real, conserva evidencia de:

- imagen original;
- configuración `provider_config_snapshot`;
- texto OCR bruto;
- logs `ocr` y `llm_structuring`;
- registros estructurados;
- depósitos persistidos;
- archivo Excel si aplica.
