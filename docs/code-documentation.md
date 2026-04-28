# Documentación en código

## Propósito

Definir cómo mantener documentación técnica dentro del código backend (docstrings en Python)
alineada con los contratos reales.

## Convención usada

- Lenguaje: Python.
- Convención principal: docstrings en módulos, clases y funciones públicas.
- Comentarios inline: solo para decisiones no obvias o reglas de negocio complejas.

## Módulos actualmente documentados (alto impacto)

- `MCP_back/settings.py`
- `MCP_back/urls.py`
- `apps/api/views.py`
- `apps/api/auth.py`
- `apps/api/serializers.py`
- `apps/documents/services/upload_service.py`
- `apps/processing/models.py`
- `apps/processing/services/orchestrator.py`
- `apps/processing/services/job_runner.py`
- `apps/processing/services/manual_corrections.py`
- `apps/processing/services/settings_service.py`
- `apps/extraction/services/ocr_service.py`
- `apps/common/middleware/request_id.py`
- `apps/common/logging.py`
- `apps/api/services/tool_dispatcher.py`
- `apps/api/services/shared_tools.py`
- `mcp_server/server.py`
- `mcp_server/api_client.py`
- `mcp_server/schemas.py`
- `scripts/debug_processing_pipeline.py`
- `scripts/init_mariadb.py`
- `scripts/verify_mariadb.py`

## Qué debe explicar cada docstring

- Propósito del módulo/clase/función.
- Parámetros y retorno cuando la firma no basta.
- Errores esperables.
- Efectos secundarios (DB, archivos, llamadas externas, hilos).
- Supuestos clave del negocio (estados de job, fallback OCR, seguridad API key).

## Módulos críticos para mantener al día

- Capa REST: `apps/api/views.py`, `apps/api/serializers.py`.
- Pipeline: `apps/processing/services/orchestrator.py`.
- Runtime config: `apps/processing/services/settings_service.py`.
- Integración OCR/LLM: `apps/extraction/services/ocr_service.py`.

## Pendiente de documentación on-code

- Revisar tests complejos para agregar intención cuando el nombre no sea suficiente.
- Homogeneizar estilo de docstrings en todos los servicios del asistente para incluir
  sección explícita de errores y efectos secundarios cuando aplique.

## Enlaces relacionados

- [Arquitectura](architecture.md)
- [API](api.md)
- [Integraciones](integrations.md)

