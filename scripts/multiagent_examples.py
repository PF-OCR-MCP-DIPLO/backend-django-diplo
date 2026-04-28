"""
Ejemplo de uso de la arquitectura de multiagentes.

Este archivo demuestra cómo se integran los agentes en un flujo real.
"""

# ============================================================================
# EJEMPLO 1: Validación simple de un registro
# ============================================================================

from apps.processing.services.validation_agent import ValidationAgent

validation_agent = ValidationAgent()

# Registro extraído del LLM
record = {
    "referencia": "TRX-2025-001234",
    "valor": "10500.50",
    "fecha_consignacion": "27/04/2025",
    "hora_consignacion": "14:30",
}

result = validation_agent.validate_record(record)

print(f"Registro válido: {result.is_valid}")
print(f"Confianza: {result.confidence_score:.2f}")
print(f"Requiere revisión: {result.needs_review}")
print(f"Issues: {result.validation_issues}")

# ============================================================================
# EJEMPLO 2: Limpieza de texto OCR
# ============================================================================

from apps.processing.services.cleaning_agent import CleaningAgent

cleaning_agent = CleaningAgent()

# Texto bruto del OCR (con errores)
raw_text = """
Comprobante de Depósito
Banco Principal
Referencia: TRX-2025-O01234  (nótese la O en lugar de 0)
Monto: $ 10,OOO.50  (caracteres mal interpretados)
Fecha: 27-04-2025
Hora: 14:3O
"""

result = cleaning_agent.run(raw_text, None)

print(f"Texto limpio:\n{result.cleaned_text}")
print(f"Confianza de limpieza: {result.confidence_score:.2f}")
print(f"Correcciones aplicadas: {result.corrections_applied}")
print(f"Issues detectados: {result.issues_found}")

# ============================================================================
# EJEMPLO 3: Decisión de reintentos
# ============================================================================

from apps.processing.services.retry_agent import RetryAgent
from apps.processing.services.validation_agent import ValidationResult

retry_agent = RetryAgent()

# Simular un registro con baja confianza
poor_validation = ValidationResult(
    is_valid=False,
    confidence_score=0.45,  # Baja confianza
    needs_review=True,
)

# Decidir si reintentar
decision = retry_agent.decide(
    image_id=123,
    error_type="validation_failed",
    validation_result=poor_validation,
    current_config=None,
)

print(f"¿Reintentar? {decision.should_retry}")
print(f"Estrategia: {decision.strategy}")
print(f"Razón: {decision.reason}")
print(f"Reintentos restantes: {decision.max_retries_remaining}")

# ============================================================================
# EJEMPLO 4: Agregación de múltiples intentos
# ============================================================================

from apps.processing.services.aggregation_agent import AggregationAgent

aggregation_agent = AggregationAgent()

# Registrar intento 1 (confianza baja)
aggregation_agent.record_attempt(
    attempt_number=1,
    strategy_used="OCR:tesseract|LLM:qwen2.5",
    ocr_text="garbled text due to low quality image",
    records=[
        {"referencia": "TRX123", "valor": "10000"},
        {"referencia": "TRX456", "valor": "5000"},
    ],
    confidence=0.45,
)

# Registrar intento 2 (confianza mejor)
aggregation_agent.record_attempt(
    attempt_number=2,
    strategy_used="OCR:vision|LLM:qwen2.5",
    ocr_text="clear text from vision model",
    records=[
        {"referencia": "TRX123", "valor": "10000"},  # Consenso
        {"referencia": "TRX456", "valor": "5000"},   # Consenso
        {"referencia": "TRX789", "valor": "3000"},   # Nuevo
    ],
    confidence=0.82,
)

# Agregar resultados
aggregated = aggregation_agent.aggregate()

print(f"Mejor intento: #{aggregated.best_attempt.attempt_number}")
print(f"Registros en consenso: {len(aggregated.consensus_records)}")
print(f"Conflictos: {len(aggregated.conflicting_records)}")
print(f"Confianza agregada: {aggregated.aggregation_confidence:.2f}")
print(f"Recomendación: {aggregated.recommendation}")

summary = aggregation_agent.get_summary()
print(f"Resumen: {summary}")

# ============================================================================
# EJEMPLO 5: Flujo completo en ProcessingSupervisorAgent (ya integrado)
# ============================================================================

# En orchestrator.py:
# process_prepared_job() ahora:
# 1. Crea ProcessingSupervisorAgent con los nuevos agentes
# 2. Llama process_image() con loop de reintentos
# 3. Cada intento registra en AggregationAgent
# 4. Al final, usa Aggregation para seleccionar mejor resultado
# 5. ExtractionLog captura todo el histórico

# Ejemplo de cómo se vería:
"""
process_run = ProcessRun(...)
for source_image in process_run.source_images.all():
    supervisor = ProcessingSupervisorAgent()  # Incluye todos los agentes
    records_count = supervisor.process_image(
        process_run, source_image, runtime_config, log_callback
    )
    # supervisor orquesta:
    # 1. OCR + Cleaning
    # 2. LLM structuring
    # 3. Validation (inteligente)
    # 4. Retry logic (RetryAgent)
    # 5. Aggregation (AggregationAgent)
    # Todo automático e integrado
"""

# ============================================================================
# EJEMPLO 6: Logs generados en ExtractionLog
# ============================================================================

# Para cada imagen, se generan eventos como:
EXAMPLE_LOGS = [
    {
        "stage": "ocr_extracted",
        "provider": "ollama",
        "model": "llava:7b",
        "raw_text": "...",
    },
    {
        "stage": "cleaning_applied",
        "raw_payload": {
            "corrections_applied": 5,
            "confidence_score": 0.85,
        }
    },
    {
        "stage": "llm_structured",
        "raw_payload": {
            "records_count": 3,
        }
    },
    {
        "stage": "validation_passed",
        "raw_payload": {
            "records_validated": 3,
        }
    },
    # O en caso de retry:
    {
        "stage": "validation_failed",
        "raw_payload": {
            "failed_records": 1,
            "avg_confidence": 0.45,
        }
    },
    {
        "stage": "retry_applied",
        "raw_payload": {
            "strategy": "change_ocr_mode",
            "from": "tesseract",
            "to": "vision",
        }
    },
    {
        "stage": "validation_passed",
        "raw_payload": {
            "records_validated": 3,
        }
    },
    {
        "stage": "aggregation_summary",
        "raw_payload": {
            "total_attempts": 2,
            "consensus_records": 3,
            "aggregation_confidence": 0.82,
            "recommendation": "accept",
        }
    },
]

# ============================================================================
# NOTAS IMPORTANTES
# ============================================================================

"""
1. CONFIGURACIÓN:
   - Todos los parámetros están en .env (OLLAMA_MODEL, ASSISTANT_MODEL, etc)
   - RetryAgent.MAX_RETRIES_PER_IMAGE = 3 (configurable)
   - ValidationAgent.confidence_thresholds son configurables

2. AUDITORÍA:
   - Cada intento se registra en ExtractionLog
   - Se capturan intentos fallidos y exitosos
   - Histórico completo disponible para debugging

3. PERFORMANCE:
   - Máx 3 reintentos por imagen (predeterminado)
   - Timeout escala con cada intento
   - Agregación es O(n) donde n=intentos (típicamente 1-3)

4. INTEGRACIÓN:
   - Transparente: ProcessingSupervisorAgent maneja todo
   - No se requieren cambios en orchestrator.py
   - Backward compatible con código existente

5. PRÓXIMAS MEJORAS:
   - SplitTextAgent: dividir OCR muy largo
   - ContextAgent: usar historial de depósitos
   - ModelPerformanceAgent: aprender qué modelo funciona mejor
   - FeedbackAgent: mejorar con datos de revisión humana
"""
