# Backend Diplo Final

Backend Django para carga de documentos DOCX, extracción OCR/LLM, corrección manual
de consignaciones, exportación a Excel y chat de asistente técnico.

## Propósito funcional

El backend expone una API REST bajo `/api/` para:

- recibir documentos DOCX con imágenes embebidas,
- ejecutar un pipeline OCR + estructuración,
- permitir correcciones manuales y reprocesos parciales,
- exportar resultados,
- ofrecer endpoints de diagnóstico y asistente.

## Stack técnico verificado

- Python 3.12
- Django 6 + Django REST Framework
- MariaDB/MySQL o SQLite (según `DATABASE_URL`)
- `drf-spectacular` para OpenAPI
- Integraciones OCR/LLM con Ollama y Tesseract (con stubs para demo/testing)

## Requisitos previos

- Python 3.12
- `pip`
- Base de datos MariaDB/MySQL o SQLite local
- (Opcional) Docker y Docker Compose para entorno con MariaDB

## Instalación local

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

## Configuración local

1. Ajusta `.env` con los valores necesarios.
2. Ejecuta migraciones:

```bash
python manage.py migrate
```

3. Inicia el servidor:

```bash
python manage.py runserver
```

## Variables de entorno reales

Las variables verificadas en `MCP_back/settings.py` y `.env.example` se documentan
en detalle en `docs/configuration.md`.

Variables mínimas más usadas:

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DATABASE_URL`
- `API_KEY`
- `CORS_ALLOWED_ORIGINS`
- `PROCESS_JOBS_ASYNC`
- `STUB_PROVIDERS`
- `OCR_PROVIDER`, `LLM_PROVIDER`
- `OLLAMA_MODEL`, `OLLAMA_VISION_MODEL`, `OLLAMA_TIMEOUT`

## Comandos disponibles (verificados)

- Levantar backend: `python manage.py runserver`
- Aplicar migraciones: `python manage.py migrate`
- Crear migraciones: `python manage.py makemigrations`
- Ejecutar tests Django: `python manage.py test`
- Ejecutar lint de formato en CI: `black --check .`
- Generar schema OpenAPI: `python manage.py spectacular --file openapi.yaml`

## Pruebas y calidad

Comandos observados en CI (`.github/workflows/ci.yml`):

```bash
black --check .
python manage.py migrate --noinput
python -m coverage run manage.py test
python -m coverage report -m --fail-under=70
```

## Estructura general del proyecto

- `MCP_back/`: configuración Django (`settings`, `urls`, `wsgi`, `asgi`)
- `apps/api/`: vistas, serializers, auth y servicios del asistente
- `apps/documents/`: carga y extracción inicial de DOCX
- `apps/extraction/`: proveedores OCR/LLM y validación de extracción
- `apps/processing/`: modelos, orquestación, reprocesos, exportación y diagnóstico
- `tests/`: suite de pruebas backend
- `docs/`: documentación técnica canónica del backend

## Documentación técnica

- [Mapa documental](docs/index.md)
- [Primeros pasos](docs/getting-started.md)
- [Arquitectura](docs/architecture.md)
- [Configuración](docs/configuration.md)
- [API](docs/api.md)
- [Autenticación](docs/authentication.md)
- [Base de datos](docs/database.md)
- [Integraciones](docs/integrations.md)
- [Jobs y workers](docs/jobs-and-workers.md)
- [Documentación en código](docs/code-documentation.md)

## Troubleshooting básico

- Si falla conexión DB, revisa `DATABASE_URL` y estado de MariaDB.
- Si recibes `401`, valida header `X-API-Key` y `API_KEY`.
- Si OCR/LLM no responde, revisa modelos/configuración en `docs/integrations.md`.

## Nota sobre publicación de documentación

La documentación vive dentro del repositorio en `backend-diplo-final/docs/`.
No hay configuración de GitHub Pages ni publicación externa como parte de este backend.
