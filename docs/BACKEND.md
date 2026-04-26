# Backend

## Estructura Django

- `MCP_back/`: settings, URLs, ASGI y WSGI.
- `apps/api/`: vistas REST, serializers, permisos y helpers de error.
- `apps/processing/`: modelos de corridas, settings, logs y depósitos.
- `apps/extraction/`: schemas y proveedores OCR/LLM.
- `apps/documents/`: servicios de carga y extracción de imágenes.
- `apps/common/`: middleware de request id, logging y utilidades comunes.

## Modelos principales

- `ProcessRun`: corrida de procesamiento y artefactos de salida.
- `SourceImage`: imágenes derivadas del DOCX y su estado OCR.
- `ExtractedDeposit`: consignaciones detectadas o corregidas.
- `ProcessingSettings`: configuración singleton editable desde la UI.
- `ExtractionLog`: bitácora por etapa y por fuente.

## Serializers y views

- `UploadDocumentSerializer`: valida DOCX y tamaño máximo.
- `ProcessRunDetailSerializer`: entrega corrida con relaciones anidadas.
- `ProcessingSettingsSerializer`: oculta claves reales y expone flags de presencia.
- `apps/api/views.py`: concentra health, jobs, exportación, reproceso, settings y chat.

## Servicios de procesamiento

- `job_runner.py`: arranque y coordinación de ejecuciones.
- `orchestrator.py`: flujo principal de procesamiento.
- `manual_corrections.py`: correcciones y reprocesos específicos.
- `excel_exporter.py`: exportación a Excel.
- `diagnostics.py`: resumen de estado y salud.
- `settings_service.py`: lectura y persistencia de configuración.

## Seguridad y API key

- `ApiKeyPermission` valida `X-API-Key`.
- `ALLOW_OPEN_API_FOR_DEV` permite la API abierta solo en desarrollo.
- `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS` se derivan de entorno.

