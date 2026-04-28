# Diagrama de Estructura de Datos - MariaDB

## 📊 Diagrama Entidad-Relación (ER)

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUJO DE PROCESAMIENTO OCR                   │
└─────────────────────────────────────────────────────────────────┘

USUARIO SUBE DOCX
       │
       ▼
┌──────────────────────────────────────┐
│    processing_processrun             │
├──────────────────────────────────────┤
│ • id (PK)                            │
│ • source_docx (FileField)            │◄─── Archivo DOCX original
│ • original_filename (CharField)      │
│ • extracted_text (TextField)         │◄─── Texto total extraído
│ • status (CharField)                 │     UPLOADED → PROCESSING →
│ • total_images (PositiveInt)         │     COMPLETED → COMPLETED_
│ • total_records (PositiveInt)        │     WITH_ERRORS → FAILED
│ • excel_file (FileField, nullable)   │◄─── Archivo Excel de salida
│ • error_message (TextField)          │
│ • created_at, updated_at             │
└──────┬───────────────────────────────┘
       │
       │ 1 ProcessRun: N SourceImages
       │
       ▼
┌──────────────────────────────────────┐
│    processing_sourceimage            │
├──────────────────────────────────────┤
│ • id (PK)                            │
│ • process_run_id (FK)────────────────┼──► ProcessRun
│ • sequence_index (PositiveInt)       │
│ • image_file (FileField)             │◄─── Imagen extraída DOCX
│ • source_name (CharField)            │
│ • content_hash (CharField)           │
│ • ocr_status (CharField)             │     PENDING → PROCESSED →
│ • ocr_raw_text (TextField)           │◄─── Texto OCR raw
│ • ocr_provider (CharField)           │
│ • error_message (TextField)          │
│ • created_at, updated_at             │
│                                      │
│ UNIQUE: (process_run_id, seq_idx)   │
└──────┬───────────────────────────────┘
       │
       │ 1 SourceImage: N ExtractedDeposits
       │
       ▼
┌──────────────────────────────────────┐
│  processing_extracteddeposit         │
├──────────────────────────────────────┤
│ • id (PK)                            │
│ • process_run_id (FK)────────────────┼──► ProcessRun
│ • source_image_id (FK)───────────────┼──► SourceImage
│ • sequence_index (PositiveInt)       │
│ • fecha_consignacion (CharField)     │◄─── Fecha de consignación
│ • hora_consignacion (CharField)      │
│ • referencia (CharField)             │◄─── Número referencia
│ • valor (DecimalField)               │◄─── Valor en dinero
│ • is_current_month (BooleanField)    │
│ • observations (JSONField)           │◄─── Notas/observaciones
│ • structured_payload (JSONField)     │◄─── Datos estructurados
│ • created_at                         │
└──────────────────────────────────────┘


┌──────────────────────────────────────┐
│ processing_processingSettings        │
├──────────────────────────────────────┤
│ • id (PK)                            │
│ • singleton_key (CharField, UNIQUE)  │ ◄──  Config global (1 registro)
│ • ocr_mode (CharField)               │      tesseract/vision/auto
│ • ocr_provider (CharField)           │      ollama/openai/gemini...
│ • ocr_model (CharField)              │
│ • llm_provider (CharField)           │
│ • llm_model (CharField)              │
│ • assistant_provider (CharField)     │
│ • assistant_model (CharField)        │
│ • ocr_api_key (CharField)            │
│ • llm_api_key (CharField)            │
│ • assistant_api_key (CharField)      │
│ • assistant_temperature (Float)      │
│ • assistant_num_predict (Int)        │
│ • extraction_criteria (JSONField)    │
│ • created_at, updated_at             │
└──────────────────────────────────────┘


┌──────────────────────────────────────┐
│  processing_extractionlog            │
├──────────────────────────────────────┤
│ • id (PK)                            │
│ • process_run_id (FK)────────────────┼──► ProcessRun
│ • source_image_id (FK, nullable)─────┼──► SourceImage
│ • sequence_index (PositiveInt)       │
│ • stage (CharField)                  │     extract/ocr/parse/export
│ • provider (CharField)               │     ollama/openai/etc
│ • model (CharField)                  │     qwen/gpt/etc
│ • ocr_mode (CharField)               │
│ • raw_payload (JSONField)            │◄─── Respuesta completa API
│ • raw_text (TextField)               │◄─── Texto crudo
│ • notes (TextField)                  │     Notas técnicas
│ • is_error (BooleanField)            │
│ • created_at                         │
└──────────────────────────────────────┘
```

## 🔗 Relaciones

### ProcessRun → SourceImage (1:N)
- **1 ProcessRun** puede tener **N SourceImages**
- Cuando se elimina ProcessRun, se eliminan sus SourceImages (CASCADE)

### ProcessRun → ExtractedDeposit (1:N)
- **1 ProcessRun** puede tener **N ExtractedDeposits**
- Cuando se elimina ProcessRun, se eliminan sus ExtractedDeposits (CASCADE)

### SourceImage → ExtractedDeposit (1:N)
- **1 SourceImage** puede originar **N ExtractedDeposits**
- Cuando se elimina SourceImage, se eliminan sus ExtractedDeposits (CASCADE)

### SourceImage → ExtractionLog (1:N)
- **1 SourceImage** puede tener **N ExtractionLogs**
- Para auditoría y debugging

### ProcessRun → ExtractionLog (1:N)
- **1 ProcessRun** puede tener **N ExtractionLogs**
- Para bitácora completa del proceso

## 📈 Flujo de Datos Típico

```
1. UPLOAD
   └─► Crear ProcessRun (status: uploaded)
       └─► Crear SourceImages (1 por imagen en DOCX)

2. EXTRACCIÓN DE IMÁGENES
   └─► Actualizar ProcessRun.total_images
   └─► ExtractionLog.stage = "extract"

3. OCR
   ├─► Actualizar SourceImage.ocr_raw_text
   ├─► Actualizar SourceImage.ocr_status (pending → processed)
   └─► ExtractionLog.stage = "ocr"

4. PARSEO
   ├─► Crear ExtractedDeposit (1+ por SourceImage)
   ├─► Llenar: fecha, referencia, valor, etc.
   └─► ExtractionLog.stage = "parse"

5. CORRECCIÓN (opcional)
   └─► Actualizar ExtractedDeposit.observations
   └─► ExtractionLog.stage = "correction"

6. EXPORTACIÓN
   ├─► Generar Excel
   ├─► Guardar en ProcessRun.excel_file
   ├─► Actualizar ProcessRun.status (completed)
   └─► ExtractionLog.stage = "export"
```

## 📊 Consultas Útiles

### Todos los ProcessRuns con su estado
```sql
SELECT 
    id, 
    original_filename, 
    status, 
    total_images, 
    total_records,
    created_at
FROM processing_processrun
ORDER BY created_at DESC;
```

### Detalles de un ProcessRun
```sql
SELECT 
    pr.id,
    pr.original_filename,
    pr.status,
    COUNT(DISTINCT si.id) as num_images,
    COUNT(DISTINCT ed.id) as num_deposits,
    SUM(ed.valor) as valor_total
FROM processing_processrun pr
LEFT JOIN processing_sourceimage si ON pr.id = si.process_run_id
LEFT JOIN processing_extracteddeposit ed ON pr.id = ed.process_run_id
WHERE pr.id = ?
GROUP BY pr.id;
```

### OCR con errores
```sql
SELECT 
    si.id,
    si.source_name,
    si.ocr_status,
    si.error_message,
    si.created_at
FROM processing_sourceimage si
WHERE si.ocr_status = 'failed'
ORDER BY si.created_at DESC;
```

### Consignaciones por mes
```sql
SELECT 
    DATE(ed.created_at) as fecha,
    COUNT(*) as cantidad,
    SUM(ed.valor) as total
FROM processing_extracteddeposit ed
GROUP BY DATE(ed.created_at)
ORDER BY fecha DESC;
```

### Auditoría completa de un ProcessRun
```sql
SELECT 
    el.sequence_index,
    el.stage,
    el.provider,
    el.model,
    CASE WHEN el.is_error THEN 'ERROR' ELSE 'OK' END as status,
    el.notes,
    el.created_at
FROM processing_extractionlog el
WHERE el.process_run_id = ?
ORDER BY el.sequence_index, el.created_at;
```

## 💾 Índices Creados Automáticamente

Django crea automáticamente:
- **PK** en todos los `id`
- **FK** en todas las relaciones
- **UNIQUE** en `(process_run_id, sequence_index)` para SourceImage

Considerar agregar manualmente:
```sql
-- Índices para búsquedas comunes
CREATE INDEX idx_processrun_status ON processing_processrun(status);
CREATE INDEX idx_sourceimage_status ON processing_sourceimage(ocr_status);
CREATE INDEX idx_extracteddeposit_fecha ON processing_extracteddeposit(fecha_consignacion);
CREATE INDEX idx_extractionlog_stage ON processing_extractionlog(stage);

-- Índices para joins frecuentes
CREATE INDEX idx_sourceimage_process_run ON processing_sourceimage(process_run_id);
CREATE INDEX idx_extracteddeposit_source_image ON processing_extracteddeposit(source_image_id);
```

## 🔐 Constraints

- **ATOMIC_REQUESTS = True**: Todas las operaciones en transacción
- **sql_mode = 'STRICT_TRANS_TABLES'**: Modo estricto MySQL
- **charset = utf8mb4**: Soporte completo Unicode
- **ON DELETE CASCADE**: Eliminar registros padre elimina hijos

## 📝 Campos JSON (Estructura)

### ExtractedDeposit.observations
```json
[
  {
    "corrected_by": "usuario@example.com",
    "field": "referencia",
    "old_value": "123456",
    "new_value": "123457",
    "timestamp": "2024-04-27T10:30:00Z",
    "reason": "Dígito invertido en OCR"
  }
]
```

### ExtractedDeposit.structured_payload
```json
{
  "raw_values": {
    "fecha": "27/04/2024",
    "hora": "10:30",
    "referencia": "DEPO-123456",
    "valor": "1.500.000"
  },
  "parsed": {
    "fecha_consignacion": "27/04/2024",
    "hora_consignacion": "10:30",
    "referencia": "DEPO-123456",
    "valor": 1500000.00
  },
  "confidence": 0.95,
  "model_used": "qwen3.5:9b"
}
```

### ExtractionLog.raw_payload
```json
{
  "provider": "ollama_vision",
  "model": "bakllava:latest",
  "status": "success",
  "response": {
    "text": "Texto extraído...",
    "confidence": 0.92
  },
  "processing_time_ms": 1234,
  "tokens_used": 450
}
```

### ProcessingSettings.extraction_criteria
```json
{
  "fields": [
    {
      "name": "fecha_consignacion",
      "pattern": "dd/mm/yyyy",
      "required": true
    },
    {
      "name": "referencia",
      "pattern": "[A-Z0-9-]+",
      "required": true
    },
    {
      "name": "valor",
      "type": "decimal",
      "required": true
    }
  ],
  "validation_rules": [
    "fecha <= today()",
    "valor > 0",
    "referencia not empty"
  ]
}
```
