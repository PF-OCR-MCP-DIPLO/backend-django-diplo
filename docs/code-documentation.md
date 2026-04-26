# Documentación interna del código

Esta guía define cómo documentar el código fuente del backend Django desde
dentro, sin reemplazar la documentación externa de MkDocs.

## Objetivo

La documentación interna debe explicar responsabilidad, contrato, entradas,
salidas, efectos secundarios, errores, decisiones de seguridad y flujos de
OCR/LLM, corrección manual, exportación y MCP.

## Qué se documenta dentro del código

- Docstrings en módulos, clases, serializers, views, servicios y providers.
- Comentarios inline solo cuando expliquen una decisión no evidente.
- Tests complejos cuando la intención del caso no se deduce por el nombre.

## Qué se documenta en MkDocs

MkDocs se reserva para arquitectura, runbooks, ADRs, testing y operación.

## Convenciones

- Explicar contrato, dependencias, transacciones y efectos secundarios.
- Aclarar campos sensibles, write-only/read-only y validaciones relevantes.
- Documentar timeout, fallback y límites de los providers OCR/LLM.

## Cuándo comentar inline

- Cuando un fallback OCR evita perder texto útil.
- Cuando un flujo conserva resultados parciales para reproceso posterior.
- Cuando una validación tiene un motivo de seguridad.

## Cuándo evitar comentarios

- Si el docstring ya cubre la intención.
- Si el comentario solo repite la línea de código.
- Si la intención no puede confirmarse, dejar una nota explícita.

## Contratos frontend-backend

- Mantener alineados serializers y tipos cliente.
- Documentar qué endpoint consume cada flujo de UI.
- Explicar estados de proceso y errores esperados.

## Efectos secundarios

Documentar transacciones, escrituras en storage, reprocesos y exportaciones.

## Errores

Documentar validaciones, conflictos de estado, timeouts y fallos parciales.

## Tests

- Documentar solo pruebas complejas o contraintuitivas.
- Explicar el caso de negocio protegido por la prueba.

