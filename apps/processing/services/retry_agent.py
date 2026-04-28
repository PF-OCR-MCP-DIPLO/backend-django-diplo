"""
Retry Agent: Decide estrategia de reintentos inteligentes.

Responsable de:
- Analizar por qué falló
- Decidir si reintentar
- Seleccionar estrategia (cambiar modelo, OCR mode, etc)
- Limitar reintentos para evitar loops infinitos
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RetryStrategy(str, Enum):
    """Estrategias disponibles para reintentos."""
    CHANGE_OCR_MODE = "change_ocr_mode"  # Tesseract → Vision
    CHANGE_LLM_MODEL = "change_llm_model"  # Modelo más potente
    INCREASE_TIMEOUT = "increase_timeout"  # Más tiempo
    SPLIT_TEXT = "split_text"  # Dividir OCR en chunks
    INCREASE_CONFIDENCE = "increase_confidence"  # Requerir más confianza
    MANUAL_REVIEW = "manual_review"  # Requiere revisión humana
    SKIP = "skip"  # No reintentar


@dataclass
class RetryDecision:
    """Decisión del agente de reintentos."""
    should_retry: bool
    strategy: RetryStrategy
    reason: str
    max_retries_remaining: int
    next_ocr_mode: Optional[str] = None
    next_llm_model: Optional[str] = None
    next_timeout_multiplier: float = 1.0


class RetryAgent:
    """Agente especializado en decisiones de reintentos inteligentes."""

    # Configuración de reintentos
    MAX_RETRIES_PER_IMAGE = 3
    MAX_RETRY_TIMEOUT_MULTIPLIER = 2.0
    CONFIDENCE_THRESHOLD_FOR_AUTO_RETRY = 0.5
    CONFIDENCE_THRESHOLD_FOR_MANUAL_REVIEW = 0.3

    def __init__(self):
        """Inicializa el agente."""
        self.retry_counts = {}  # Tracking de reintentos por imagen

    def decide(
        self,
        image_id: int,
        error_type: str,
        validation_result=None,
        current_config=None,
        previous_attempts: list = None,
    ) -> RetryDecision:
        """
        Decide si reintentar y con qué estrategia.
        
        Args:
            image_id: ID de la imagen siendo procesada
            error_type: Tipo de error ("ocr_failed", "extraction_failed", "validation_failed", "timeout")
            validation_result: Resultado de validación del ValidationAgent
            current_config: Configuración actual (ProcessingSettings)
            previous_attempts: Historia de intentos previos
            
        Returns:
            RetryDecision con estrategia y parámetros
        """
        retry_count = self.retry_counts.get(image_id, 0)
        retries_remaining = self.MAX_RETRIES_PER_IMAGE - retry_count

        # Si ya alcanzó máximo reintentos, no reintentar más
        if retries_remaining <= 0:
            return RetryDecision(
                should_retry=False,
                strategy=RetryStrategy.MANUAL_REVIEW,
                reason=f"Max retries ({self.MAX_RETRIES_PER_IMAGE}) reached",
                max_retries_remaining=0,
            )

        # Determinar estrategia basada en tipo de error
        if error_type == "ocr_failed":
            return self._handle_ocr_failure(image_id, retries_remaining, current_config)
        elif error_type == "extraction_failed":
            return self._handle_extraction_failure(image_id, retries_remaining, current_config)
        elif error_type == "validation_failed":
            return self._handle_validation_failure(
                image_id, retries_remaining, validation_result, current_config
            )
        elif error_type == "timeout":
            return self._handle_timeout(image_id, retries_remaining, current_config)
        else:
            return RetryDecision(
                should_retry=False,
                strategy=RetryStrategy.SKIP,
                reason=f"Unknown error type: {error_type}",
                max_retries_remaining=retries_remaining,
            )

    def _handle_ocr_failure(
        self, image_id: int, retries_remaining: int, current_config
    ) -> RetryDecision:
        """Maneja fallo en OCR."""
        current_mode = current_config.ocr_mode if current_config else "auto"

        # Si estamos en Tesseract, cambiar a Vision
        if current_mode == "tesseract":
            self.retry_counts[image_id] = self.retry_counts.get(image_id, 0) + 1
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.CHANGE_OCR_MODE,
                reason="Tesseract failed, switching to Vision mode",
                max_retries_remaining=retries_remaining - 1,
                next_ocr_mode="vision",
            )

        # Si estamos en Vision, incrementar timeout
        if current_mode == "vision":
            self.retry_counts[image_id] = self.retry_counts.get(image_id, 0) + 1
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.INCREASE_TIMEOUT,
                reason="Vision mode failed, increasing timeout",
                max_retries_remaining=retries_remaining - 1,
                next_timeout_multiplier=1.5,
            )

        # Si estamos en auto, cambiar a vision
        if current_mode == "auto":
            self.retry_counts[image_id] = self.retry_counts.get(image_id, 0) + 1
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.CHANGE_OCR_MODE,
                reason="Auto mode failed, forcing Vision",
                max_retries_remaining=retries_remaining - 1,
                next_ocr_mode="vision",
            )

        # Sin más opciones de OCR
        return RetryDecision(
            should_retry=False,
            strategy=RetryStrategy.MANUAL_REVIEW,
            reason="All OCR modes exhausted",
            max_retries_remaining=retries_remaining,
        )

    def _handle_extraction_failure(
        self, image_id: int, retries_remaining: int, current_config
    ) -> RetryDecision:
        """Maneja fallo en extracción (LLM)."""
        current_model = current_config.llm_model if current_config else "default"

        # Primer intento: aumentar timeout
        if self.retry_counts.get(image_id, 0) == 0:
            self.retry_counts[image_id] = 1
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.INCREASE_TIMEOUT,
                reason="LLM extraction failed, increasing timeout",
                max_retries_remaining=retries_remaining - 1,
                next_timeout_multiplier=1.5,
            )

        # Segundo intento: cambiar modelo
        if self.retry_counts.get(image_id, 0) == 1:
            self.retry_counts[image_id] = 2
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.CHANGE_LLM_MODEL,
                reason="Extraction timeout, trying different LLM model",
                max_retries_remaining=retries_remaining - 1,
                next_llm_model=self._select_alternative_model(current_model),
                next_timeout_multiplier=2.0,
            )

        # Sin más opciones
        return RetryDecision(
            should_retry=False,
            strategy=RetryStrategy.MANUAL_REVIEW,
            reason="LLM extraction exhausted retry options",
            max_retries_remaining=retries_remaining,
        )

    def _handle_validation_failure(
        self, image_id: int, retries_remaining: int, validation_result, current_config
    ) -> RetryDecision:
        """Maneja fallo en validación."""
        if not validation_result:
            return RetryDecision(
                should_retry=False,
                strategy=RetryStrategy.SKIP,
                reason="No validation result provided",
                max_retries_remaining=retries_remaining,
            )

        confidence = validation_result.confidence_score

        # Si la confianza es baja pero >30%, reintentar con mejor modelo
        if self.CONFIDENCE_THRESHOLD_FOR_MANUAL_REVIEW < confidence < self.CONFIDENCE_THRESHOLD_FOR_AUTO_RETRY:
            if self.retry_counts.get(image_id, 0) < 2:
                self.retry_counts[image_id] = self.retry_counts.get(image_id, 0) + 1
                return RetryDecision(
                    should_retry=True,
                    strategy=RetryStrategy.CHANGE_LLM_MODEL,
                    reason=f"Low confidence ({confidence:.2f}), trying better model",
                    max_retries_remaining=retries_remaining - 1,
                    next_llm_model=self._select_better_model(
                        current_config.llm_model if current_config else "default"
                    ),
                )

        # Si la confianza es muy baja, enviar a revisión
        if confidence <= self.CONFIDENCE_THRESHOLD_FOR_MANUAL_REVIEW:
            return RetryDecision(
                should_retry=False,
                strategy=RetryStrategy.MANUAL_REVIEW,
                reason=f"Very low confidence ({confidence:.2f}), requires manual review",
                max_retries_remaining=retries_remaining,
            )

        # Si la confianza es aceptable, no reintentar
        return RetryDecision(
            should_retry=False,
            strategy=RetryStrategy.SKIP,
            reason=f"Acceptable confidence ({confidence:.2f}), no retry needed",
            max_retries_remaining=retries_remaining,
        )

    def _handle_timeout(
        self, image_id: int, retries_remaining: int, current_config
    ) -> RetryDecision:
        """Maneja timeout."""
        retry_count = self.retry_counts.get(image_id, 0)

        # Primer timeout: aumentar timeout
        if retry_count == 0:
            self.retry_counts[image_id] = 1
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.INCREASE_TIMEOUT,
                reason="Timeout occurred, increasing request timeout",
                max_retries_remaining=retries_remaining - 1,
                next_timeout_multiplier=1.5,
            )

        # Segundo timeout: cambiar a modo más rápido
        if retry_count == 1:
            self.retry_counts[image_id] = 2
            return RetryDecision(
                should_retry=True,
                strategy=RetryStrategy.CHANGE_OCR_MODE,
                reason="Still timing out, switching to faster OCR mode",
                max_retries_remaining=retries_remaining - 1,
                next_ocr_mode="tesseract",  # Más rápido
            )

        # Sin más opciones
        return RetryDecision(
            should_retry=False,
            strategy=RetryStrategy.MANUAL_REVIEW,
            reason="Repeated timeouts, unable to process",
            max_retries_remaining=retries_remaining,
        )

    def _select_alternative_model(self, current_model: str) -> str:
        """Selecciona un modelo alternativo diferente al actual."""
        # Mapeo de modelos alternativos
        alternatives = {
            "qwen2.5:7b": "llama3.1:8b",
            "llama3.1:8b": "mistral:7b",
            "mistral:7b": "neural-chat:7b",
            "neural-chat:7b": "qwen2.5:7b",
        }
        return alternatives.get(current_model, "llama3.1:8b")

    def _select_better_model(self, current_model: str) -> str:
        """Selecciona un modelo más potente que el actual."""
        # Ordenados por "potencia" aproximada
        model_hierarchy = [
            "qwen2.5:7b",
            "neural-chat:7b",
            "mistral:7b",
            "llama3.1:8b",
            "qwen2.5:14b",
        ]

        try:
            current_index = model_hierarchy.index(current_model)
            # Seleccionar el siguiente modelo más potente
            if current_index < len(model_hierarchy) - 1:
                return model_hierarchy[current_index + 1]
        except ValueError:
            pass

        # Default a modelo más potente
        return "llama3.1:8b"

    def reset_image_retries(self, image_id: int):
        """Resetea contador de reintentos para una imagen."""
        self.retry_counts.pop(image_id, None)

    def reset_all_retries(self):
        """Resetea todos los contadores de reintentos."""
        self.retry_counts.clear()
