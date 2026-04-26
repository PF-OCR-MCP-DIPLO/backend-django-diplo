# Troubleshooting

## 401 / API key

- Causa: header faltante o incorrecto.
- Diagnóstico: revisar `X-API-Key`.
- Solución: sincronizar frontend y backend.

## Procesamiento lento

- Causa: proveedor OCR/LLM lento.
- Diagnóstico: revisar logs y provider health.
- Solución: usar stub providers en demo o ampliar timeouts.

