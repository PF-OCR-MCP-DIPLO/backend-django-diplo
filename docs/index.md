# Índice de documentación backend

Este índice es el mapa canónico de documentación de `backend-diplo-final/`.

## Orden recomendado de lectura

1. [Primeros pasos](getting-started.md)
2. [Arquitectura](architecture.md)
3. [Configuración](configuration.md)
4. [Desarrollo](development.md)
5. [Contrato API](api-contract.md)
6. [Pipeline de procesamiento](processing-pipeline.md)
7. [Troubleshooting OCR](ocr-troubleshooting.md)
8. [API](api.md)
9. [Autenticación](authentication.md)
10. [Base de datos](database.md)
11. [Integraciones](integrations.md)
12. [Jobs y workers](jobs-and-workers.md)
13. [Testing](testing.md)
14. [Troubleshooting](troubleshooting.md)
15. [Documentación en código](code-documentation.md)

## Mapa documental

- [getting-started.md](getting-started.md): instalación rápida, ejecución local y flujo mínimo.
- [architecture.md](architecture.md): módulos reales, flujo end-to-end y decisiones operativas.
- [configuration.md](configuration.md): variables de entorno y configuración de runtime.
- [development.md](development.md): comandos de desarrollo, scripts y prácticas del repo.
- [api-contract.md](api-contract.md): contrato HTTP consumido por el frontend.
- [processing-pipeline.md](processing-pipeline.md): flujo DOCX, OCR, LLM, validación,
  persistencia, exportación y diagnóstico.
- [ocr-troubleshooting.md](ocr-troubleshooting.md): diagnóstico de OCR, binarización y
  regresiones de calidad.
- [testing.md](testing.md): estrategia de tests y comandos verificados desde CI/código.
- [troubleshooting.md](troubleshooting.md): fallos frecuentes y diagnóstico guiado.
- [api.md](api.md): rutas REST reales y contratos observables.
- [authentication.md](authentication.md): seguridad por API key y supuestos.
- [database.md](database.md): modelos, relaciones y persistencia.
- [integrations.md](integrations.md): OCR/LLM y dependencias externas.
- [jobs-and-workers.md](jobs-and-workers.md): procesamiento síncrono/asíncrono y reprocesos.
- [code-documentation.md](code-documentation.md): convención de docstrings y módulos críticos.
- [adr/README.md](adr/README.md): registro de decisiones arquitectónicas (ADR).

## Referencia histórica

- [archive/README.md](archive/README.md): inventario de documentación heredada.
- Documentos legacy fuera de `docs/` fueron reclasificados o absorbidos; si algún dato
  histórico no está trazado aquí, queda **Pendiente de validar**.

## Pendiente de validar

- Compatibilidad de toda la documentación legacy de migración MariaDB con entornos
  productivos no locales.
- Alcance operativo de flujos MCP fuera del uso cubierto por tests y código backend actual.
