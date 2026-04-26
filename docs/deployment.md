# Deployment

## Preparación

1. Configurar `DEBUG=0`.
2. Configurar `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` y `API_KEY`.
3. Ejecutar migraciones.
4. Revisar CORS y CSRF.
5. Asegurar almacenamiento de media.

## Qué no subir

- `db.sqlite3`
- `media/`
- secretos en `.env`

