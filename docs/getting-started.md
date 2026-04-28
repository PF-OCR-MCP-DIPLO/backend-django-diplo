# Primeros pasos

## Propósito

Poner en marcha el backend localmente con configuración verificable desde el código.

## Requisitos

- Python 3.12
- `pip`
- Base de datos accesible (SQLite para debug o MariaDB/MySQL por `DATABASE_URL`)

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

## Arranque local

```bash
python manage.py migrate
python manage.py runserver
```

API disponible en `http://localhost:8000/api/`.

## Arranque con Docker Compose

El repositorio incluye `docker-compose.yml` con servicios `mariadb`, `backend` y `frontend`.
Si usas este archivo desde backend, toma en cuenta que también intenta construir frontend
desde `../Frontend-diplo`.

## Flujo mínimo de uso

1. Verifica salud con `GET /api/health/`.
2. Sube DOCX con `POST /api/documents/upload/`.
3. Procesa con `POST /api/jobs/{id}/process/`.
4. Consulta resultados en `GET /api/jobs/{id}/`.

## Enlaces relacionados

- [Configuración](configuration.md)
- [API](api.md)
- [Jobs y workers](jobs-and-workers.md)
- [Troubleshooting](troubleshooting.md)
