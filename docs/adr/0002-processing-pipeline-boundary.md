# ADR 0002: Separación del pipeline de procesamiento

## Estado
Inferida por estructura actual

## Contexto
El procesamiento necesita validación, OCR, estructuración, corrección y exportación.

## Decisión
Separar views, servicios de dominio y proveedores externos.

## Consecuencias
- Pipeline más fácil de probar.
- Mejor aislamiento entre API y lógica de negocio.
- Más trazabilidad en logs y diagnósticos.
