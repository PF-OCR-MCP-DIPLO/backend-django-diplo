# Desarrollo local

## Requisitos

- Python 3.12
- Dependencias instaladas desde `requirements.txt`
- Base de datos configurada por `DATABASE_URL` o SQLite en debug

## Arranque

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Problemas comunes

- Si `python` no existe, usar `python3`.
- Si faltan dependencias, revisar el entorno virtual.
- Si el backend rechaza la petición, revisar `API_KEY`.

