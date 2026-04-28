"""
Aggregation Agent: Combina resultados de múltiples intentos de extracción.

Responsable de:
- Mantener histórico de intentos
- Combinar registros de múltiples estrategias
- Seleccionar el mejor resultado
- Crear consenso entre intentos
"""

from dataclasses import dataclass, field
from typing import Optional
from decimal import Decimal


@dataclass
class ExtractionAttempt:
    """Un intento de extracción."""

    attempt_number: int
    strategy_used: str
    ocr_text: str
    records: list
    confidence: float
    error: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class AggregatedResult:
    """Resultado final agregado de múltiples intentos."""

    best_attempt: ExtractionAttempt
    all_attempts: list[ExtractionAttempt]
    consensus_records: list  # Registros en los que concuerdan los intentos
    conflicting_records: list  # Registros con discrepancias
    aggregation_confidence: float
    recommendation: str  # "accept", "review", "reject"


class AggregationAgent:
    """Agente especializado en agregar resultados de múltiples intentos."""

    def __init__(self):
        """Inicializa el agente."""
        self.attempts_history = []  # Historia de intentos

    def record_attempt(
        self,
        attempt_number: int,
        strategy_used: str,
        ocr_text: str,
        records: list,
        confidence: float,
        error: Optional[str] = None,
    ) -> ExtractionAttempt:
        """
        Registra un intento de extracción.

        Args:
            attempt_number: Número de intento (1, 2, 3...)
            strategy_used: Estrategia utilizada (OCR mode, model, etc)
            ocr_text: Texto OCR extraído
            records: Registros estructurados extraídos
            confidence: Score de confianza
            error: Si hubo error, descripción

        Returns:
            ExtractionAttempt registrado
        """
        attempt = ExtractionAttempt(
            attempt_number=attempt_number,
            strategy_used=strategy_used,
            ocr_text=ocr_text,
            records=records,
            confidence=confidence,
            error=error,
        )
        self.attempts_history.append(attempt)
        return attempt

    def aggregate(self) -> Optional[AggregatedResult]:
        """
        Agrega todos los intentos registrados.

        Returns:
            AggregatedResult con consenso y recomendación
        """
        if not self.attempts_history:
            return None

        # Seleccionar mejor intento
        best_attempt = max(
            self.attempts_history, key=lambda a: a.confidence if not a.error else 0.0
        )

        # Identificar registros en consenso
        consensus_records, conflicting_records = self._find_consensus(
            self.attempts_history
        )

        # Calcular confianza de agregación
        aggregation_confidence = self._calculate_aggregation_confidence(
            best_attempt, consensus_records, conflicting_records
        )

        # Generar recomendación
        recommendation = self._generate_recommendation(
            best_attempt, aggregation_confidence, consensus_records, conflicting_records
        )

        return AggregatedResult(
            best_attempt=best_attempt,
            all_attempts=self.attempts_history,
            consensus_records=consensus_records,
            conflicting_records=conflicting_records,
            aggregation_confidence=aggregation_confidence,
            recommendation=recommendation,
        )

    def _find_consensus(self, attempts: list) -> tuple[list, list]:
        """
        Identifica registros que aparecen en múltiples intentos.

        Un registro está en consenso si:
        - Referencia y monto coinciden en >= 2 intentos
        - O solo hay 1 intento exitoso
        """
        if not attempts:
            return [], []

        # Crear firma de cada registro (referencia + valor)
        record_signatures = {}
        for attempt in attempts:
            if attempt.error:
                continue
            for record in attempt.records:
                sig = self._create_record_signature(record)
                if sig not in record_signatures:
                    record_signatures[sig] = []
                record_signatures[sig].append((attempt, record))

        consensus_records = []
        conflicting_records = []

        # Analizar coincidencias
        for sig, occurrences in record_signatures.items():
            if len(occurrences) >= 2:
                # Consenso: aparece en múltiples intentos
                # Usar el de mayor confianza
                best_record = max(occurrences, key=lambda x: x[0].confidence)
                consensus_records.append(best_record[1])
            else:
                # Sin consenso pero único intento exitoso
                if len(attempts) == 1 or all(att.error for att in attempts[:-1]):
                    consensus_records.append(occurrences[0][1])
                else:
                    conflicting_records.append(occurrences[0][1])

        return consensus_records, conflicting_records

    def _create_record_signature(self, record: dict) -> str:
        """Crea una firma única del registro para comparación."""
        referencia = record.get("referencia", "").strip().upper()
        valor = str(record.get("valor", "")).strip()
        return f"{referencia}|{valor}"

    def _calculate_aggregation_confidence(
        self, best_attempt: ExtractionAttempt, consensus: list, conflicts: list
    ) -> float:
        """Calcula confianza agregada."""
        score = best_attempt.confidence

        # Bonus si hay consenso múltiple
        if consensus and len(self.attempts_history) > 1:
            consensus_ratio = len(consensus) / max(1, len(self.attempts_history) * 3)
            score += min(0.2, consensus_ratio * 0.3)

        # Penalidad si hay conflictos
        if conflicts:
            conflict_ratio = len(conflicts) / max(1, len(consensus) + len(conflicts))
            score -= min(0.3, conflict_ratio * 0.2)

        # Bonus si múltiples intentos concuerdan
        if len(self.attempts_history) > 1:
            successful_attempts = [a for a in self.attempts_history if not a.error]
            if len(successful_attempts) >= 2:
                score += 0.15

        return max(0.0, min(1.0, score))

    def _generate_recommendation(
        self,
        best: ExtractionAttempt,
        confidence: float,
        consensus: list,
        conflicts: list,
    ) -> str:
        """Genera recomendación de qué hacer con los resultados."""
        # Alta confianza y consenso → ACCEPT
        if confidence >= 0.7 and len(conflicts) == 0:
            return "accept"

        # Confianza media y algo de consenso → REVIEW
        if confidence >= 0.5 and len(consensus) > 0:
            return "review"

        # Baja confianza o muchos conflictos → REJECT (requiere reproceso)
        return "reject"

    def clear_history(self):
        """Limpia el histórico de intentos."""
        self.attempts_history.clear()

    def get_summary(self) -> dict:
        """Retorna resumen de intentos para auditoría."""
        return {
            "total_attempts": len(self.attempts_history),
            "successful_attempts": len(
                [a for a in self.attempts_history if not a.error]
            ),
            "average_confidence": (
                sum(a.confidence for a in self.attempts_history)
                / len(self.attempts_history)
                if self.attempts_history
                else 0.0
            ),
            "strategies_used": [a.strategy_used for a in self.attempts_history],
            "errors": [a.error for a in self.attempts_history if a.error],
        }
