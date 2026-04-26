# Modelos

## ProcessRun

- Unidad principal de trazabilidad.
- Guarda archivo fuente, estado, totales, exportación y timestamps.

## SourceImage

- Una fila por imagen extraída.
- Preserva `sequence_index`.
- Relacionada a `ProcessRun`.

## ExtractedDeposit

- Resultado estructurado editable.
- Relacionada a `ProcessRun` y `SourceImage`.

## ProcessingSettings

- Singleton de configuración operativa.
- Guarda proveedores, claves y criterios.

## ExtractionLog

- Bitácora técnica por etapa.
- Sirve para diagnóstico y chat asistido.

