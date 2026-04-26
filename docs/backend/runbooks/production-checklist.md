# Runbook: checklist de producción

- `DJANGO_DEBUG=0`
- `DJANGO_SECRET_KEY` configurada
- `DJANGO_ALLOWED_HOSTS` configurado
- `DATABASE_URL` configurada
- `API_KEY` configurada
- `CORS_ALLOWED_ORIGINS` configurado
- `CSRF_TRUSTED_ORIGINS` configurado
- `SECURE_SSL_REDIRECT` revisado
- `SECURE_HSTS_SECONDS` revisado
- `MEDIA_ROOT` persistente
- Logs accesibles
- Timeouts revisados
- Backups definidos
- Migraciones aplicadas
- Static files validados

## Riesgo de producción

Pendiente de confirmar si el despliegue usará almacenamiento compartido para
media o un objeto externo compatible.
