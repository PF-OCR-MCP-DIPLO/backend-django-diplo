# Pipeline de procesamiento

```mermaid
flowchart LR
    A[Upload DOCX] --> B[Extract images]
    B --> C[OCR]
    C --> D[LLM structuring]
    D --> E[Validation]
    E --> F[Manual corrections]
    F --> G[Excel export]
```

## Fallos parciales

- Una imagen puede fallar sin invalidar toda la corrida.
- El estado final puede ser `completed_with_errors`.
- El reproceso puede apuntar a fallos completos o a una sola fuente.

