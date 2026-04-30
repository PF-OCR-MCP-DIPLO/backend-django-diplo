# Pipeline backend

Esta página conserva la ubicación histórica dentro de `docs/backend/`.

La documentación mantenible del flujo DOCX, OCR, estructuración, validación,
persistencia, exportación, diagnóstico y binarización vive en:

- [../processing-pipeline.md](../processing-pipeline.md)
- [../ocr-troubleshooting.md](../ocr-troubleshooting.md)

## Resumen operativo

1. `DocumentUploadView` recibe el `.docx`.
2. `create_process_run_from_upload` extrae imágenes y texto auxiliar.
3. `ProcessingSupervisorAgent` valida imagen, ejecuta OCR, limpia texto,
   estructura con LLM, valida y persiste depósitos.
4. `manual_corrections.py` permite correcciones y reprocesos parciales.
5. `excel_exporter.py` genera el archivo Excel.
6. `diagnostics.py` resume eventos, tiempos y señales de proveedor.

El flujo actual no activa binarización por defecto. Los cambios de
preprocesamiento deben validarse con `tests.test_tesseract_ocr` y
`tests.test_ocr_pipeline_stability`.
