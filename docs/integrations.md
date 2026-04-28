# Integraciones externas

## Propósito

Describir dependencias externas del backend verificadas en código.

## OCR

- Tesseract (`apps/extraction/providers/ocr/tesseract.py`)
- Ollama Vision (`apps/extraction/providers/ocr/ollama_vision.py`)
- Stub OCR para demo/testing (`apps/extraction/providers/ocr/stub.py`)

`extract_raw_text` aplica fallback por modo (`tesseract`, `vision`, `auto`) y conserva
metadatos de intentos para auditoría.

## LLM de estructuración

- Ollama text (`apps/extraction/providers/llm/ollama_text.py`)
- Stub LLM (`apps/extraction/providers/llm/stub.py`)

Proveedores adicionales (`openai`, `gemini`, `deepseek`, `anthropic`) aparecen en catálogos
de configuración, pero su operación en este MVP queda restringida o no implementada.

## MCP

- Componentes en `mcp_server/` y tests de paridad/contrato (`tests/test_mcp_*.py`).
- Detalle funcional completo del uso MCP en operación real: **Pendiente de validar**.

## Dependencias de infraestructura

- MariaDB en `docker-compose.yml`.
- Docker para entorno reproducible local.

## Riesgos de integración

- Disponibilidad y timeout de Ollama.
- Calidad de OCR dependiente de la imagen.
- Divergencias entre modo stub y modo real.

## Enlaces relacionados

- [Configuración](configuration.md)
- [Jobs y workers](jobs-and-workers.md)
- [Troubleshooting](troubleshooting.md)
