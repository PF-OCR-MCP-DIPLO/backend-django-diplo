# Seguridad

## Baseline

- `API_KEY` protege escrituras y lectura sensible cuando está configurada.
- `DJANGO_SECRET_KEY` es obligatoria en producción.
- `DJANGO_ALLOWED_HOSTS` no debe quedar vacío fuera de debug.
- `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS` deben limitarse a orígenes reales.

## Checklist

- `DEBUG=0`
- `SECRET_KEY` real
- `API_KEY` real
- `ALLOWED_HOSTS` reales
- `CORS` restringido
- `MEDIA_ROOT` con permisos adecuados
- `SECURE_SSL_REDIRECT` revisado

