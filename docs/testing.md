# Testing

## Propósito

Describir cómo validar el backend con comandos y suites reales del repositorio.

## Comandos verificados

```bash
python manage.py test
python -m coverage run manage.py test
python -m coverage report -m --fail-under=70
```

`black --check .` se ejecuta en CI como control de formato.

## Cobertura funcional observada

- Contratos de API (`tests/test_api*.py`, `tests/test_api_contracts.py`).
- Pipeline OCR/LLM y estabilidad (`tests/test_ocr_pipeline_stability.py`,
  `tests/test_extraction_providers.py`, `tests/test_tesseract_ocr.py`).
- Asistente y herramientas (`tests/test_assistant_*.py`, `tests/test_pending_actions.py`,
  `tests/test_deposit_correction_tools.py`).
- Integración MCP (`tests/test_mcp_contract.py`, `tests/test_mcp_parity.py`).
- Exportación y validadores (`tests/test_excel_exporter.py`, `tests/test_validators.py`).

## Criterio mínimo de calidad actual (CI)

- Formato `black` sin cambios.
- Tests Django pasando.
- Cobertura mínima de 70%.

## Pendiente de validar

- Uso oficial de `pytest` como runner principal. El CI actual usa `manage.py test`.

## Enlaces relacionados

- [Desarrollo](development.md)
- [API](api.md)
- [Jobs y workers](jobs-and-workers.md)
