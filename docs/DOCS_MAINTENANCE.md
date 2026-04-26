# Mantenimiento de documentación

## Cuándo actualizar

- Cambia una ruta frontend.
- Cambia un endpoint backend.
- Cambia una variable de entorno.
- Cambia un modelo o serializer.
- Cambia el pipeline de procesamiento.
- Cambia el despliegue o los scripts de build.

## Checklist de PR

- Los cambios de código están reflejados en docs.
- No quedaron afirmaciones sin verificar.
- Los enlaces de MkDocs siguen válidos.
- El README sigue siendo breve.

## Mantener sincronía

1. Actualizar el código.
2. Actualizar el documento canónico.
3. Repetir en el archivo histórico solo si aporta contexto.
4. Validar con `mkdocs build --strict`.
