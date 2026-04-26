# Auditoría interna del código

## Resumen

- Cobertura ampliada en API, services de assistant, processing helpers, MCP y
  tests de contrato.
- Persisten módulos secundarios y vistas largas sin una segunda pasada
  completa.

## Archivos documentados en esta ronda

- `apps/api/services/assistant_chat.py`
- `apps/api/services/assistant_tasks.py`
- `apps/api/services/pending_actions.py`
- `apps/api/services/shared_tools.py`
- `apps/api/services/tool_dispatcher.py`
- `apps/api/services/tool_risk.py`
- `apps/extraction/providers/llm/*`
- `apps/extraction/providers/ocr/*`
- `apps/extraction/schemas.py`
- `apps/extraction/services/image_validation.py`
- `apps/extraction/services/validators.py`
- `apps/processing/services/diagnostics.py`
- `apps/processing/services/excel_exporter.py`
- `apps/processing/services/extraction_criteria.py`
- `apps/processing/services/job_cleanup.py`
- `apps/processing/services/job_runner.py`
- `apps/processing/services/ollama_models.py`
- `apps/processing/services/settings_service.py`
- `mcp_server/api_client.py`
- `mcp_server/schemas.py`
- `mcp_server/server.py`
- `apps/documents/services/upload_service.py`
- `apps/documents/services/docx_image_extractor.py`
- `apps/extraction/services/ocr_service.py`
- `apps/extraction/services/structuring_service.py`
- `apps/processing/models.py`
- `apps/processing/services/manual_corrections.py`
- `apps/processing/services/orchestrator.py`
- `apps/extraction/providers/ocr/base.py`

## Pendientes prioritarios

- `apps/api/views.py`
- `apps/api/serializers.py`
- `apps/api/auth.py`
- `apps/api/errors.py`
- `apps/api/exception_handlers.py`
- `apps/api/views.py`
- `apps/api/serializers.py`
- `apps/api/services/assistant_agent.py`
- `apps/api/services/assistant_llm.py`
- `apps/api/services/assistant_multiagent.py`
- `apps/api/services/deposit_correction_tools.py`
- `apps/processing/services/job_runner.py`
- `apps/processing/services/orchestrator.py` revisión adicional
- `apps/common/*`
- `MCP_back/settings.py`
- `MCP_back/urls.py`
- `tests/test_api.py`
- `tests/test_assistant_*.py`
- `tests/test_mcp_*.py`
- `tests/test_processing_diagnostics.py`

## Contrato inferido por uso

- La API de UI espera payloads normalizados y rutas resueltas a media.
- El pipeline conserva trazabilidad para reproceso parcial.
- Los proveedores OCR/LLM exponen fallback y errores que la UI resume.
- Las acciones pendientes deben confirmarse antes de mutar datos persistentes.
- El servidor MCP reutiliza el mismo contrato JSON que la API HTTP.

## Pendiente de confirmar

- Qué vistas API largas requieren una segunda pasada por submódulos y helpers.

## Siguiente ronda

1. Cerrar `apps/api/views.py` y `apps/api/serializers.py` por completo.
2. Documentar `assistant_agent`, `assistant_multiagent` y `deposit_correction_tools`.
3. Revisar `MCP_back/settings.py`, `MCP_back/urls.py` y tests de API/assistant.
