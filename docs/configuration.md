# Configuración

## Propósito

Documentar la configuración real del backend según `MCP_back/settings.py` y `.env.example`.

## Variables de entorno verificadas

### Núcleo Django

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_TIME_ZONE`
- `LOG_LEVEL`
- `APP_VERSION`

### Base de datos

- `DATABASE_URL`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_ROOT_PASSWORD`

### Seguridad y acceso API

- `API_KEY`
- `ALLOW_OPEN_API_FOR_DEV`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `MCP_ENABLE_MUTATIONS`

### Pipeline y límites

- `PROCESS_JOBS_ASYNC`
- `DOCX_MAX_UPLOAD_BYTES`
- `DOCX_MAX_IMAGES`
- `EXTRACTED_IMAGE_MAX_BYTES`
- `MAX_OCR_CHARS_FOR_LLM`
- `TESSERACT_TIMEOUT_SECONDS`

### OCR/LLM

- `STUB_PROVIDERS`
- `OCR_PROVIDER`
- `LLM_PROVIDER`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `OLLAMA_VISION_MODEL`
- `OLLAMA_TIMEOUT`
- `LLM_MAX_RETRIES`
- `LLM_RETRY_DELAY`

### Hardening de producción

- `SECURE_SSL_REDIRECT`
- `SECURE_HSTS_SECONDS`

## Reglas relevantes de configuración

- Si `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` y `API_KEY` son obligatorias.
- Si no hay `DATABASE_URL` y `DJANGO_DEBUG=1`, se usa SQLite local.
- `ALLOW_OPEN_API_FOR_DEV` solo puede estar activo en debug.

## Archivo de referencia

- Plantilla local: `.env.example`

## Pendiente de validar

- Convención final de secrets para despliegues productivos externos al entorno local.
- Si todas las variables de hardening se inyectan por plataforma de despliegue o por `.env`.

## Enlaces relacionados

- [Primeros pasos](getting-started.md)
- [Desarrollo](development.md)
- [Autenticación](authentication.md)
