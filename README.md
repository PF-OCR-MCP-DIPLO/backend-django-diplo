# backend-diplo-final

Backend Django para carga de documentos, OCR/LLM, corrección manual, exportación
y chat de asistente.

## Ruta canónica

- [Inicio de documentación](docs/index.md)
- [Arquitectura](docs/architecture/overview.md)
- [API REST](docs/backend/api.md)
- [Pipeline de procesamiento](docs/backend/processing-pipeline.md)
- [Integración frontend-backend](docs/integration/frontend-backend.md)
- [Testing](docs/TESTING.md)
- [Deployment](docs/deployment.md)
- [Runbooks operativos](docs/backend/runbooks/local-stack.md)
- [Mantenimiento de docs](docs/DOCS_MAINTENANCE.md)

## Uso rápido

```bash
python manage.py migrate
python manage.py runserver
```

## Documentación

- La documentación canónica vive en `docs/`.
- La documentación heredada se conserva en `docs/archive/` y en la navegación
  marcada como histórica.
- La validación local de docs usa `mkdocs build --strict`.
