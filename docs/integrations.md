# Integraciones externas

## Propósito

Describir dependencias externas verificadas en código para OCR, LLM, MCP y
runtime local.

## OCR

| Integración | Código | Estado |
| --- | --- | --- |
| Tesseract | `apps/extraction/providers/ocr/tesseract.py` | Operativa si el binario y el idioma existen |
| Ollama Vision | `apps/extraction/providers/ocr/ollama_vision.py` | Operativa con Ollama accesible y modelo instalado |
| Stub OCR | `apps/extraction/providers/ocr/stub.py` | Operativa con `STUB_PROVIDERS=1` |
| OpenAI/Gemini/DeepSeek | Catálogo de settings | No implementadas para OCR en este MVP |

`extract_raw_text` aplica modos `tesseract`, `vision` y `auto`, y conserva
metadatos de intentos para auditoría.

El preprocesamiento compartido vive en `preprocess_image_for_ocr`. El flujo
actual no activa binarización por defecto; consulta
[ocr-troubleshooting.md](ocr-troubleshooting.md) antes de modificar esa etapa.

## LLM de estructuración

| Integración | Código | Estado |
| --- | --- | --- |
| Ollama text | `apps/extraction/providers/llm/ollama_text.py` | Operativa con Ollama accesible |
| Stub LLM | `apps/extraction/providers/llm/stub.py` | Operativa con `STUB_PROVIDERS=1` |
| OpenAI/Gemini/DeepSeek/Anthropic | Catálogo de settings | No operativas en este MVP |

La estructuración usa `LLM_MAX_RETRIES`, `LLM_RETRY_DELAY`,
`request_timeout_seconds`, `MAX_OCR_CHARS_FOR_LLM` y `extraction_criteria`.

## Ollama

Variables relevantes:

- `OLLAMA_BASE_URL`;
- `OLLAMA_URL`;
- `OLLAMA_TAGS_URL`;
- `OLLAMA_MODEL`;
- `OLLAMA_VISION_MODEL`;
- `OLLAMA_TIMEOUT`.

Endpoints de soporte:

- `GET /api/processing/ollama/models/`;
- `GET /api/processing/provider-health/`.

## Tesseract

El `Dockerfile` instala:

- `tesseract-ocr`;
- `libtesseract-dev`;
- `tesseract-ocr-spa`.

En local fuera de Docker debes instalar el binario y los idiomas requeridos en
el sistema operativo.

## MCP

- Componentes en `mcp_server/`.
- Tests de contrato y paridad en `tests/test_mcp_*.py`.
- Mutaciones controladas por `MCP_ENABLE_MUTATIONS`.
- Uploads restringibles con `MCP_ALLOWED_UPLOAD_ROOTS`.

## Riesgos de integración

- Ollama puede responder lento o no tener el modelo solicitado.
- Tesseract depende del binario del sistema y de paquetes de idioma.
- Proveedores stub no reflejan calidad real.
- Cambios de preprocesamiento pueden alterar texto OCR y registros persistidos.

## Enlaces relacionados

- [Configuración](configuration.md)
- [Pipeline de procesamiento](processing-pipeline.md)
- [Troubleshooting OCR](ocr-troubleshooting.md)
- [Jobs y workers](jobs-and-workers.md)
