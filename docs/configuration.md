# Configuración

## Propósito

Documentar las variables de entorno verificadas en `MCP_back/settings.py`,
`.env.example`, `Dockerfile` y `docker-compose.yml`.

## Reglas generales

- En debug (`DJANGO_DEBUG=1`) y sin `DATABASE_URL`, el backend usa SQLite.
- En producción (`DJANGO_DEBUG=0`) son obligatorias `DJANGO_SECRET_KEY`,
  `DJANGO_ALLOWED_HOSTS` y `API_KEY`.
- `ALLOW_OPEN_API_FOR_DEV` solo puede estar activo en debug.
- Los valores secretos no deben versionarse. Usa `.env` local o variables del
  entorno de despliegue.

## Núcleo Django

| Variable | Uso | Default observado |
| --- | --- | --- |
| `DJANGO_DEBUG` | Activa modo debug | `1` |
| `DJANGO_SECRET_KEY` | Clave Django | Valor inseguro solo dev |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos | `localhost,127.0.0.1` en debug |
| `DJANGO_TIME_ZONE` | Zona horaria | `America/Bogota` |
| `LOG_LEVEL` | Nivel de logging raíz | `INFO` |
| `APP_VERSION` | Versión OpenAPI | `0.1.0` |

## Base de datos

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | URL principal de conexión |
| `DB_HOST` | Host usado por scripts/compose |
| `DB_PORT` | Puerto MariaDB/MySQL |
| `DB_NAME` | Nombre de BD |
| `DB_USER` | Usuario de BD |
| `DB_PASSWORD` | Password de BD |
| `DB_ROOT_PASSWORD` | Password root en Docker Compose |

Ejemplo local MariaDB:

```env
DATABASE_URL=mysql://mcp_user:mcp_secure_2026@localhost:3306/mcp_db
```

## Seguridad y CORS

| Variable | Uso |
| --- | --- |
| `API_KEY` | Valor esperado en `X-API-Key` |
| `ALLOW_OPEN_API_FOR_DEV` | Permite API abierta solo en debug |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos |
| `CSRF_TRUSTED_ORIGINS` | Orígenes confiables para CSRF |
| `SECURE_SSL_REDIRECT` | Redirección HTTPS |
| `SECURE_HSTS_SECONDS` | HSTS |

## Límites del pipeline

| Variable | Uso | Default observado |
| --- | --- | --- |
| `PROCESS_JOBS_ASYNC` | Jobs en background | `1` |
| `DOCX_MAX_UPLOAD_BYTES` | Tamaño máximo DOCX | `10485760` |
| `DOCX_MAX_IMAGES` | Máximo de imágenes por DOCX | `50` |
| `EXTRACTED_IMAGE_MAX_BYTES` | Tamaño máximo por imagen | `5242880` |
| `MAX_OCR_CHARS_FOR_LLM` | Texto OCR máximo hacia LLM | `8000` |
| `TESSERACT_TIMEOUT_SECONDS` | Timeout de Tesseract | `60` en settings |
| `STUB_PROVIDERS` | Proveedores determinísticos | `0` |

## OCR y LLM

| Variable | Uso |
| --- | --- |
| `OCR_MODE` | Modo por defecto: `tesseract`, `vision`, `auto` |
| `OCR_PROVIDER` | Proveedor OCR base |
| `OCR_MODEL` | Idioma Tesseract o modelo OCR |
| `LLM_PROVIDER` | Proveedor LLM base |
| `LLM_MODEL` | Modelo de estructuración |
| `LLM_MAX_RETRIES` | Reintentos LLM |
| `LLM_RETRY_DELAY` | Pausa entre reintentos |
| `OCR_TEMPERATURE` | Parámetro OCR definido en settings |
| `OCR_NUM_PREDICT` | Parámetro OCR definido en settings |

## Ollama

| Variable | Uso |
| --- | --- |
| `OLLAMA_BASE_URL` | Base URL de Ollama |
| `OLLAMA_URL` | Endpoint `/api/generate` |
| `OLLAMA_TAGS_URL` | Endpoint `/api/tags` |
| `OLLAMA_MODEL` | Modelo LLM por defecto |
| `OLLAMA_VISION_MODEL` | Modelo de visión por defecto |
| `OLLAMA_TIMEOUT` | Timeout general |
| `OLLAMA_OCR_NUM_PREDICT` | Límite de tokens para OCR visión |
| `OLLAMA_AUTO_VISION_TIMEOUT_SECONDS` | Timeout visión en modo `auto` |
| `OLLAMA_VISION_TIMEOUT_SECONDS` | Timeout visión en modo `vision` |
| `OLLAMA_LLM_TIMEOUT_SECONDS` | Timeout LLM |
| `AUTO_OCR_ACCEPT_SCORE` | Score mínimo para aceptar Tesseract en `auto` |

Algunas variables de Ollama no aparecen en `.env.example`, pero se leen en
código con defaults internos.

## Asistente

| Variable | Uso |
| --- | --- |
| `ASSISTANT_MODEL` | Modelo del asistente |
| `ASSISTANT_TEMPERATURE` | Temperatura del asistente |
| `ASSISTANT_NUM_PREDICT` | Límite de generación |

## MCP

| Variable | Uso |
| --- | --- |
| `MCP_ENABLE_MUTATIONS` | Habilita mutaciones MCP |
| `MCP_ALLOWED_UPLOAD_ROOTS` | Raíces permitidas para uploads MCP |

## Configuración editable por API

`GET/PATCH /api/processing/settings/` persiste el singleton
`ProcessingSettings`. Sus valores efectivos pueden sobrescribir defaults del
entorno para OCR, LLM, asistente, timeout, periodo válido y criterios de
extracción.

Las API keys de proveedores se guardan como campos write-only y solo se reporta
si existen mediante `has_ocr_api_key`, `has_llm_api_key` y
`has_assistant_api_key`.

## Enlaces relacionados

- [Primeros pasos](getting-started.md)
- [Desarrollo](development.md)
- [Pipeline de procesamiento](processing-pipeline.md)
- [Autenticación](authentication.md)
