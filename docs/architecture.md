# Arquitectura del backend

## Propósito

Describir la arquitectura real observada en `backend-diplo-final/`, sin inferencias no
respaldadas por código.

## Módulos principales

- `MCP_back/`: configuración Django (`settings.py`, `urls.py`).
- `apps/api/`: capa HTTP (vistas DRF, serializers, permisos por API key, servicios de asistente).
- `apps/documents/`: ingestión DOCX y extracción inicial de texto/imágenes.
- `apps/extraction/`: proveedores OCR/LLM y validación/estructuración.
- `apps/processing/`: dominio del pipeline, modelos, diagnósticos, exportación y reproceso.
- `apps/common/`: middleware de request id y utilidades compartidas.
- `mcp_server/`: integración MCP (alcance operativo detallado **Pendiente de validar**).

## Flujo principal end-to-end

1. Upload de DOCX (`DocumentUploadView`) crea `ProcessRun` + `SourceImage`.
2. Inicio de procesamiento (`JobProcessView`) delega en `job_runner` y `orchestrator`.
3. OCR/LLM procesa cada imagen y persiste `ExtractedDeposit` + `ExtractionLog`.
4. Corrección manual permite ajustar depósitos sin reprocesar todo el job.
5. Exportación genera Excel asociado a la corrida.

## Capas de responsabilidad

- **Presentación REST**: validación de entrada/salida, control de estado HTTP.
- **Servicios de aplicación**: orquestación de casos de uso (upload, process, export, chat).
- **Dominio/persistencia**: entidades Django (`ProcessRun`, `SourceImage`, `ExtractedDeposit`,
  `ProcessingSettings`, `ExtractionLog`).
- **Integración externa**: OCR (Tesseract/Ollama Vision) y LLM (Ollama text / proveedores declarados).

## Decisiones técnicas observadas

- API protegida por `X-API-Key` (excepto health y aperturas explícitas en debug).
- Soporte de ejecución asíncrona básica con `threading` para jobs.
- Trazabilidad operativa por eventos (`ExtractionLog`) y snapshots de configuración.
- OpenAPI generado con `drf-spectacular`.

## Riesgos técnicos

- Ejecución asíncrona en hilo local no reemplaza un sistema de colas dedicado.
- Integraciones de proveedores no `ollama` aparecen declaradas pero no operativas en MVP.
- Parte de documentación histórica de migración DB no está alineada con mantenimiento continuo.

## Enlaces relacionados

- [API](api.md)
- [Configuración](configuration.md)
- [Integraciones](integrations.md)
- [Jobs y workers](jobs-and-workers.md)
- [Base de datos](database.md)

