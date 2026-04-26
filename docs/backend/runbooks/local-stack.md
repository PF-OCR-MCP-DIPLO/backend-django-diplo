# Runbook: stack local

## Levantar backend

```bash
python manage.py migrate
python manage.py runserver
```

## Validar salud

- `GET /api/health/`
- `GET /api/schema/`
- `GET /api/docs/`

## Conectar frontend

- `VITE_API_BASE_URL=http://localhost:8000/api`
- `VITE_API_KEY=dev` si el backend lo exige
- `CORS_ALLOWED_ORIGINS=http://localhost:5173`

## Probar flujo básico

1. Subir un `.docx`.
2. Procesar el job.
3. Ver logs y estado.
4. Corregir un depósito.
5. Exportar Excel.
