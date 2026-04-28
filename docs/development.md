# Desarrollo

## Propósito

Definir flujo de trabajo local y comandos de desarrollo verificados para el backend.

## Comandos base

```bash
python manage.py migrate
python manage.py runserver
python manage.py test
```

## Comandos de calidad observados en CI

```bash
black --check .
python -m coverage run manage.py test
python -m coverage report -m --fail-under=70
```

## Scripts del repositorio

- `scripts/init_mariadb.py`
- `scripts/verify_mariadb.py`
- `scripts/debug_processing_pipeline.py`
- `scripts/init_mariadb.sh`
- `init_mariadb.bat`

## Convenciones de mantenimiento documental

- Toda documentación activa debe vivir en `README.md` y `docs/`.
- Contenido histórico va a `docs/archive/`.
- Si no hay respaldo en código/config/tests: marcar como **Pendiente de validar**.

## Pendiente de validar

- Flujo estándar del equipo para lint adicional a `black` (no aparece comando explícito
  adicional en CI actual).

## Enlaces relacionados

- [Configuración](configuration.md)
- [Testing](testing.md)
- [Troubleshooting](troubleshooting.md)
- [Documentación en código](code-documentation.md)
