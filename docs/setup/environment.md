# Variables de entorno

| Variable | Ejemplo | Obligatoria | Aplica | Riesgo |
| --- | --- | --- | --- | --- |
| `DJANGO_DEBUG` | `1` | Sí | Todos | Afecta validaciones de producción |
| `DJANGO_SECRET_KEY` | `change-me` | Sí en prod | Todos | Secreta |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Sí en prod | Todos | Bloquea acceso si falta |
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Sí en prod | Todos | Persistencia incorrecta |
| `API_KEY` | `dev` | Sí en prod | API | Protege endpoints |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174` | Recomendado | API | CORS mal configurado |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174` | Recomendado | API | CSRF en navegadores |
| `PROCESS_JOBS_ASYNC` | `1` | No | Procesamiento | Cambia el modo de ejecución |
| `STUB_PROVIDERS` | `1` | No | Demo/test | Usa proveedores deterministas |

