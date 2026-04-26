# Testing Backend

## Ejecución

```bash
pytest
python -m pytest
python manage.py test
```

## Qué cubren los tests

- Contratos de API y respuestas JSON.
- Paridad entre MCP y API pública.
- Proveedores OCR/LLM y estabilidad de la tubería.
- Exportación Excel, utilidades, seguridad y validaciones.
- Smoke tests del flujo de aplicación.

## Convenciones

- Probar contratos y efectos observables.
- Preferir fixtures pequeñas y aserciones sobre el payload real.
- Documentar casos de error cuando una vista tenga ramas no obvias.

