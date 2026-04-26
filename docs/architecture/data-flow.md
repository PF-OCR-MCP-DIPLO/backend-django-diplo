# Flujo de datos

```mermaid
flowchart TD
    A[POST /api/documents/upload/] --> B[Upload service]
    B --> C[ProcessRun + SourceImage]
    C --> D[OCR provider]
    D --> E[LLM structuring]
    E --> F[Validation]
    F --> G[ExtractedDeposit + ExtractionLog]
    G --> H[Excel export]
```

## Flujo principal

1. El upload valida el DOCX.
2. Se extraen imágenes preservando orden.
3. Cada imagen pasa por OCR.
4. La salida se estructura con LLM.
5. Se validan campos y se persisten depósitos.
6. Se registran logs y diagnósticos.
7. El usuario puede corregir y exportar.

