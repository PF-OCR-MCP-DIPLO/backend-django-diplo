# Base de datos

## Propósito

Documentar el modelo de persistencia real del backend a partir de `apps/processing/models.py`
y configuración de `MCP_back/settings.py`.

## Motores soportados

- SQLite (fallback en debug sin `DATABASE_URL`).
- MariaDB/MySQL vía `DATABASE_URL` con opciones de charset `utf8mb4`.
- PostgreSQL declarado por parser de URL.

## Entidades principales

- `ProcessRun`: corrida de procesamiento (estado, archivos, contadores, snapshot de config).
- `SourceImage`: imagen fuente derivada del DOCX y estado OCR.
- `ExtractedDeposit`: consignación estructurada y corregible.
- `ProcessingSettings`: singleton de configuración OCR/LLM/asistente.
- `ExtractionLog`: eventos y trazas de diagnóstico del pipeline.

## Relaciones clave

- `ProcessRun` 1:N `SourceImage`
- `ProcessRun` 1:N `ExtractedDeposit`
- `SourceImage` 1:N `ExtractedDeposit`
- `ProcessRun` 1:N `ExtractionLog`
- `SourceImage` 1:N `ExtractionLog` (opcional)

## Notas operativas

- Se persisten artefactos en `MEDIA_ROOT` (`source_docx`, imágenes y exportaciones).
- `provider_config_snapshot` y `raw_payload` guardan trazabilidad técnica del runtime.
- El backend usa migraciones Django en `apps/processing/migrations/`.

## Referencia histórica

- Información extensa de estructura SQL histórica permanece en `docs/DATABASE_STRUCTURE.md`.

## Pendiente de validar

- Estrategia de particionado/retención para crecimiento de `ExtractionLog` en producción.

## Enlaces relacionados

- [Arquitectura](architecture.md)
- [Configuración](configuration.md)
- [Jobs y workers](jobs-and-workers.md)
