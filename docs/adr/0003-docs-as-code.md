# ADR 0003: Docs as code con MkDocs

## Estado
Aceptado

## Contexto
La documentación necesita navegarse, versionarse y validarse en CI.

## Decisión
Usar MkDocs para documentación estática versionada.

## Consecuencias
- Navegación consistente.
- Validación con `mkdocs build --strict`.
- Publicación futura sencilla con GitHub Pages.
