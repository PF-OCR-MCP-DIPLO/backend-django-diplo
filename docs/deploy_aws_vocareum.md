# Despliegue en AWS Vocareum con Docker Compose

## Objetivo

Preparar una primera versión productiva simple en una sola instancia EC2 de
Vocareum con estos servicios:

- `mariadb`
- `backend` Django
- `frontend` React/Vite servido por Nginx

No se incluye Ollama dentro del `compose` inicial. La recomendación es usar un
endpoint externo o dejarlo apuntando al host si más adelante instalas Ollama por
fuera.

## Requisitos locales

- Docker Engine con Docker Compose plugin (`docker compose`)
- Acceso a ambos repositorios en la misma máquina:
  - `backend-diplo-final`
  - `Frontend-diplo`
- Puertos disponibles:
  - `80` para frontend y proxy reverso
  - `3306` solo interno de Docker
  - `8000` no se publica en la variante productiva actual

## Archivos de entorno

Desde el repo backend:

```sh
cp .env.production.example .env.production
cp ../Frontend-diplo/.env.production.example ../Frontend-diplo/.env.production
```

Variables backend que debes ajustar antes de AWS:

- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DATABASE_URL`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_ROOT_PASSWORD`
- `MARIADB_DATABASE`
- `MARIADB_USER`
- `MARIADB_PASSWORD`
- `MARIADB_ROOT_PASSWORD`
- `API_KEY`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `OLLAMA_BASE_URL`
- `OLLAMA_URL`
- `OLLAMA_TAGS_URL`
- `OLLAMA_MODEL`
- `OLLAMA_VISION_MODEL`

Variables frontend que debes ajustar antes de AWS:

- `VITE_API_BASE_URL=/api`
- `VITE_API_KEY`

## Configuración para EC2

Si vas a entrar por IP pública de la instancia, reemplaza `PUBLIC_IP` por la IP
real en:

- `DJANGO_ALLOWED_HOSTS=PUBLIC_IP,localhost,127.0.0.1`
- `CORS_ALLOWED_ORIGINS=http://PUBLIC_IP`
- `CSRF_TRUSTED_ORIGINS=http://PUBLIC_IP`

Si luego usas dominio, reemplaza esos valores por tu hostname.

## Build de imágenes

Desde `backend-diplo-final`:

```sh
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build
```

O usando los scripts:

```sh
./scripts/prod_up.sh
```

## Levantar servicios

```sh
docker compose -f docker-compose.prod.yml up -d
```

Servicios esperados:

- `mariadb` con volumen persistente `mariadb_data`
- `backend` Django con `gunicorn`
- `frontend` Nginx sirviendo `dist/` y haciendo proxy a `/api`

## Migraciones

El contenedor backend ejecuta automáticamente:

- espera de base de datos
- `python manage.py migrate --noinput`
- `python manage.py collectstatic --noinput`

Si quieres lanzarlas manualmente:

```sh
docker compose -f docker-compose.prod.yml exec backend python manage.py migrate --noinput
```

O:

```sh
./scripts/prod_migrate.sh
```

## Validaciones básicas

Health backend a través de Nginx:

```sh
curl http://localhost/api/health/
```

Frontend:

```sh
curl http://localhost/
```

Logs:

```sh
docker compose -f docker-compose.prod.yml logs --tail=100
```

O:

```sh
./scripts/prod_logs.sh
```

Smoke test:

```sh
./scripts/prod_smoke_test.sh
```

## Puertos para Security Group en AWS

Abrir:

- `22/tcp` para SSH
- `80/tcp` para frontend
- `8000/tcp` opcional solo si luego decides publicar backend directo para debug

## Cómo probar frontend

Abre en navegador:

- `http://PUBLIC_IP/`

La SPA quedará servida por Nginx y las llamadas API irán por `/api` al backend
interno del `compose`.

## Cómo detener servicios y ahorrar créditos

```sh
docker compose -f docker-compose.prod.yml down
```

O:

```sh
./scripts/prod_down.sh
```

Si no necesitas conservar contenedores activos, detener la instancia EC2 en
Vocareum sigue siendo la mejor forma de evitar consumo.

## Notas sobre Ollama

- No se incluye Ollama en `docker-compose.prod.yml`.
- Para el arranque inicial en Vocareum, es más seguro usar un endpoint externo o cloud.
- Si luego instalas Ollama en la misma EC2 fuera de Docker, puedes mantener:
  - `OLLAMA_BASE_URL=http://host.docker.internal:11434`
  - `OLLAMA_URL=http://host.docker.internal:11434/api/generate`
  - `OLLAMA_TAGS_URL=http://host.docker.internal:11434/api/tags`

## Nota importante sobre HTTP inicial

La configuración de ejemplo deja:

- `SECURE_SSL_REDIRECT=0`
- `SECURE_HSTS_SECONDS=0`

Esto es intencional para la primera versión en Vocareum por `http://IP_PUBLICA`.
Cuando pongas HTTPS con dominio y proxy TLS, conviene volver a endurecer esas
banderas.
