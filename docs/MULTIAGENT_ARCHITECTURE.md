# 🏗️ Arquitectura Híbrida de Multiagentes - Documentación

## 📋 Resumen Ejecutivo

Se ha implementado una **arquitectura híbrida de dos niveles** que combina:
1. **Nivel 1**: Pipeline determinístico base (OCR → Limpieza → Extracción → Validación)
2. **Nivel 2**: Capa de multiagentes inteligentes (reintentos, decisiones automáticas)

### Objetivo Principal
Mejorar la precisión, confiabilidad y recuperabilidad del pipeline OCR/LLM mediante agentes especializados que toman decisiones inteligentes basadas en confianza y contexto.

---

## 🎯 Problemas Resueltos

| Problema | Solución |
|----------|----------|
| Fallos silenciosos de OCR | CleaningAgent normalizador + validación |
| Baja precisión en extracción | ValidationAgent inteligente con confianza |
| Sin reintentos automáticos | RetryAgent con estrategias de escalada |
| Sin auditoría de intentos | AggregationAgent + logs por intento |
| Modelos fijos sin flexibilidad | Cambio dinámico de modelo/OCR mode |

---

## 🏛️ Arquitectura Técnica

### Nivel 1: Pipeline Determinístico (PRESERVADO)

```
Upload → ProcessRun Creation
    ↓
ProcessingSupervisorAgent (orquestador)
    ↓
┌─────────────────────────────────────┐
│ OCRAgent (validación + extracción)  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ StructuringAgent (LLM)              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ ValidationPersistenceAgent (guardado)│
└─────────────────────────────────────┘
```

**Características:**
- Ya existía y funciona correctamente
- Mantiene auditoría de cada fase
- Genera ExtractionLog para diagnóstico

---

### Nivel 2: Capa de Multiagentes (NUEVO)

Se agregó una capa inteligente **encima** del pipeline que:

```
Pipeline Base
    ↓
CleaningAgent (normalización)
    ↓
ValidationAgent (validación inteligente + confianza)
    ↓
¿Válido?
 ├─ Sí → AggregationAgent → Guardar
 └─ No → RetryAgent
         ├─ ¿Reintentar?
         │   ├─ Sí → LOOP (con estrategia diferente)
         │   └─ No → AggregationAgent → Guardar
         └─ Auditoría: cambio de OCR mode, modelo LLM, timeout
```

---

## 🤖 Agentes Implementados

### 1. **CleaningAgent** 
`apps/processing/services/cleaning_agent.py`

**Responsabilidad:** Normalizar y corregir texto OCR

**Características:**
- Corrección de errores comunes (O→0, l→1)
- Normalización de moneda ($10.OOO → $10000)
- Normalización de fechas (DD/MM/YYYY)
- Normalización de horas (HH:MM)
- Cálculo de confianza de limpieza

**Entrada:** Texto bruto del OCR
**Salida:** 
```python
CleaningResult(
    original_text: str,
    cleaned_text: str,
    corrections_applied: int,
    confidence_score: float,  # 0.0 - 1.0
    issues_found: list
)
```

**Ejemplo:**
```
Input:  "$ 10.OOO / 15-02-2025"
Output: "$10000 / 15/02/2025" (confidence: 0.85)
```

---

### 2. **ValidationAgent**
`apps/processing/services/validation_agent.py`

**Responsabilidad:** Validación inteligente de registros extraídos

**Características:**
- Validación de campos requeridos (referencia, valor)
- Validación de formatos y rangos
- Cálculo granular de confianza por registro
- Detección de anomalías
- Scoring de confianza basado en:
  - Validez de campos
  - Coherencia cross-field
  - Presencia de patrones esperados

**Entrada:** Registro extraído (dict)
**Salida:**
```python
ValidationResult(
    is_valid: bool,
    confidence_score: float,  # 0.0 - 1.0
    needs_review: bool,
    validation_issues: list[ValidationIssue]
)
```

**Criterios de Confianza:**
- **Confianza > 0.7**: Aceptar automáticamente
- **0.5 < Confianza ≤ 0.7**: Marcar para revisión
- **Confianza ≤ 0.5**: Reintentar o rechazar

---

### 3. **RetryAgent**
`apps/processing/services/retry_agent.py`

**Responsabilidad:** Decidir estrategia de reintentos

**Características:**
- Análisis de causa raíz del error
- Decisión inteligente de reintentos (max 3 por imagen)
- 6 estrategias de reintentos disponibles
- Escalada automática de complejidad

**Estrategias Disponibles:**
| Estrategia | Uso | Escalada |
|-----------|-----|---------|
| `CHANGE_OCR_MODE` | Tesseract → Vision | Cambiar método |
| `CHANGE_LLM_MODEL` | Modelo débil → fuerte | Mejorar capacidad |
| `INCREASE_TIMEOUT` | Falta tiempo | +50% timeout |
| `SPLIT_TEXT` | Texto muy largo | Dividir chunks (future) |
| `INCREASE_CONFIDENCE` | Umbral bajo | Requerir más confianza |
| `MANUAL_REVIEW` | Agotado | Revisión humana |

**Flujo de Decisión:**

Para **OCR Failure**:
```
Tesseract falla? → Cambiar a Vision
Vision falla? → Aumentar timeout
Sin opciones → Manual review
```

Para **Validation Failure**:
```
Confianza 0.3-0.5? → Mejor modelo
Confianza < 0.3? → Manual review
```

Para **Timeout**:
```
Primer timeout? → +50% timeout
Segundo timeout? → Cambiar a Tesseract (rápido)
```

**Entrada:** 
```python
image_id, error_type, validation_result, current_config, previous_attempts
```

**Salida:**
```python
RetryDecision(
    should_retry: bool,
    strategy: RetryStrategy,
    reason: str,
    max_retries_remaining: int,
    next_ocr_mode: str = None,
    next_llm_model: str = None,
    next_timeout_multiplier: float = 1.0
)
```

---

### 4. **AggregationAgent**
`apps/processing/services/aggregation_agent.py`

**Responsabilidad:** Agregar y consolidar resultados de múltiples intentos

**Características:**
- Registro de historico de intentos
- Detección de registros en consenso
- Identificación de conflictos
- Generación de recomendación final

**Entrada:** Múltiples intentos (cada uno con OCR text, records, confianza)

**Salida:**
```python
AggregatedResult(
    best_attempt: ExtractionAttempt,
    all_attempts: list,
    consensus_records: list,        # Acuerdos
    conflicting_records: list,      # Desacuerdos
    aggregation_confidence: float,
    recommendation: str  # "accept" | "review" | "reject"
)
```

**Consenso:** Un registro está en consenso si:
- Referencia + monto coinciden en ≥2 intentos
- O solo hay 1 intento exitoso

**Recomendaciones:**
- **"accept"**: Confianza ≥ 0.7 + sin conflictos
- **"review"**: Confianza ≥ 0.5 + consenso
- **"reject"**: Confianza < 0.5 o muchos conflictos

---

## 📊 Flujo de Procesamiento Completo

### Diagrama de Flujo (1 Imagen)

```
START
  ↓
┌─────────────────────────────────────────────────┐
│ Intento N (max 3)                              │
├─────────────────────────────────────────────────┤
│                                                 │
│  1️⃣ OCR Phase                                   │
│     ├─ Image validation                         │
│     └─ extract_raw_text() → OCR text           │
│  ↓                                              │
│  2️⃣ Cleaning Phase                              │
│     └─ CleaningAgent.run() → cleaned text      │
│  ↓                                              │
│  3️⃣ Structuring Phase                           │
│     └─ extract_structured_data() → records     │
│  ↓                                              │
│  4️⃣ Smart Validation Phase                      │
│     └─ ValidationAgent per record              │
│  ↓                                              │
│  🎯 Decision Point:                             │
│     ├─ All valid? YES → Persist & Exit         │
│     └─ Some invalid? NO → Continue             │
│  ↓                                              │
│  5️⃣ Retry Decision (RetryAgent)                │
│     ├─ Should retry?                           │
│     │  ├─ YES → Apply strategy → Next attempt  │
│     │  └─ NO → Aggregate & Persist             │
│     └─ Max retries reached? → Aggregate        │
│                                                 │
└─────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────┐
│ Aggregation Phase (AggregationAgent)            │
├─────────────────────────────────────────────────┤
│ • Select best attempt                           │
│ • Find consensus records                        │
│ • Generate recommendation                       │
│ • Log audit trail                               │
└─────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────┐
│ Persistence (ValidationPersistenceAgent)        │
├─────────────────────────────────────────────────┤
│ • Save ExtractedDeposit records                 │
│ • Update SourceImage status                     │
│ • Log final state                               │
└─────────────────────────────────────────────────┘
  ↓
END (records_count)
```

---

## 🔄 Ejemplo de Ejecución Real

### Caso: Imagen Borrosa

```
Attempt 1 (OCR: auto, LLM: qwen2.5):
  ├─ OCR text: garbled
  ├─ Cleaning confidence: 0.4
  ├─ Validation: 2/3 records invalid
  ├─ avg_confidence: 0.45
  └─ Decision: Retry (too low confidence)

  Retry Strategy: CHANGE_OCR_MODE (auto → vision)

Attempt 2 (OCR: vision, LLM: qwen2.5):
  ├─ OCR text: much better
  ├─ Cleaning confidence: 0.78
  ├─ Validation: 3/3 records valid
  ├─ avg_confidence: 0.82
  └─ Decision: Accept & Persist ✅

Aggregation Summary:
  ├─ Total attempts: 2
  ├─ Consensus records: 3
  ├─ Confidence: 0.82
  └─ Recommendation: accept
```

---

## 🔌 Integración con Sistema Existente

### Cambios Mínimos:

1. **ProcessingSupervisorAgent.process_image()**: 
   - Ahora usa loop de reintentos
   - Integra nuevos agentes automáticamente
   - Backwards compatible

2. **Logging**:
   - Cada fase genera evento ExtractionLog
   - Incluye metadata de intento/estrategia
   - Auditoría completa

3. **Database**:
   - Sin cambios de schema
   - ExtractedDeposit persiste igual
   - Metadata en ExtractionLog

---

## ⚙️ Configuración

### Parámetros de RetryAgent

En `RetryAgent.__init__()`:
```python
MAX_RETRIES_PER_IMAGE = 3  # Máximo reintentos
MAX_RETRY_TIMEOUT_MULTIPLIER = 2.0  # Timeout máximo
CONFIDENCE_THRESHOLD_FOR_AUTO_RETRY = 0.5  # Umbral p/reintentar
CONFIDENCE_THRESHOLD_FOR_MANUAL_REVIEW = 0.3  # Umbral p/revisión
```

### Parámetros de ValidationAgent

En `ValidationAgent.__init__()`:
```python
MIN_AMOUNT = Decimal('0.01')
MAX_AMOUNT = Decimal('999999999.99')
REQUIRED_FIELDS = {'referencia', 'valor'}
```

---

## 📈 Métricas y Observabilidad

### Logs Generados

Cada imagen genera eventos:

```
"ocr_extracted"           → OCR completado
"cleaning_applied"        → Limpieza aplicada
"llm_structured"          → LLM extrajo registros
"validation_passed"       → Validación exitosa ✅
"validation_failed"       → Validación falló ❌
"retry_decision_*"        → Decisión de reintento
"retry_applied"           → Estrategia aplicada
"error_*"                 → Clasificación de error
"aggregation_summary"     → Resumen final
```

### Campos en ExtractionLog

```python
{
    "stage": "retry_applied",
    "provider": runtime_config.llm_provider,
    "model": runtime_config.llm_model,
    "raw_payload": {
        "strategy": "change_ocr_mode",
        "from_ocr_mode": "tesseract",
        "to_ocr_mode": "vision",
        "attempt": 2,
        "confidence": 0.45,
    }
}
```

---

## 🎨 Beneficios Principales

✅ **Manejo de Incertidumbre**: Detecta OCR débil y cambia estrategia
✅ **Reintentos Inteligentes**: No reintentos ciegos, decisiones contextuales
✅ **Precisión Mejorada**: Validación granular + agregación
✅ **Explicabilidad**: Cada acción registrada con razón
✅ **Recuperabilidad**: Altamente resiliente a fallos temporales
✅ **Escalabilidad**: Modelos dinámicos sin cambiar código
✅ **Auditoría Completa**: Historico de todos los intentos

---

## 🚀 Próximas Mejoras Posibles

1. **SplitTextAgent**: Dividir OCR muy largo en chunks
2. **ContextAgent**: Usar historial de depósitos para mejorar confianza
3. **ModelPerformanceAgent**: Aprender qué modelo es mejor para qué imagen
4. **FeedbackAgent**: Mejorar con datos de revisión humana
5. **CostOptimizationAgent**: Seleccionar modelo más barato sin perder calidad

---

## 📚 Referencia de Código

| Componente | Ubicación | Responsabilidad |
|-----------|-----------|-----------------|
| ProcessingSupervisorAgent | `agents.py` (mejorado) | Orquestación principal |
| CleaningAgent | `cleaning_agent.py` (nuevo) | Normalización OCR |
| ValidationAgent | `validation_agent.py` (nuevo) | Validación inteligente |
| RetryAgent | `retry_agent.py` (nuevo) | Decisiones de reintentos |
| AggregationAgent | `aggregation_agent.py` (nuevo) | Agregación de intentos |

---

**Versión**: 1.0 | **Fecha**: 2026-04-27 | **Autor**: Architecture Team
