# Arquitectura general

## Capas

- Configuración: `MCP_back.settings`
- Transporte HTTP: `apps/api`
- Dominio persistente: `apps/processing`
- Entrada de documentos: `apps/documents`
- OCR/LLM: `apps/extraction`
- Integración MCP: `mcp_server`

## Decisiones relevantes

- `ProcessRun` es la unidad de trazabilidad.
- `sequence_index` preserva el orden de aparición.
- El backend usa servicios para evitar lógica pesada en las views.

## Riesgos

- Proveedores externos pueden introducir latencia y fallos transitorios.
- El modo async es in-process y no una cola distribuida.
- Los archivos en `MEDIA_ROOT` forman parte del estado operativo.

