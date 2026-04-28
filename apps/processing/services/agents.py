from apps.extraction.services.image_validation import validate_source_image
from apps.extraction.services.ocr_service import extract_raw_text
from apps.extraction.services.structuring_service import extract_structured_data
from apps.extraction.services.validators import build_record_observations
from apps.processing.models import ExtractedDeposit, SourceImage
from apps.processing.services.diagnostics import stage_timer
from apps.processing.services.cleaning_agent import CleaningAgent
from apps.processing.services.validation_agent import ValidationAgent
from apps.processing.services.retry_agent import RetryAgent, RetryStrategy
from apps.processing.services.aggregation_agent import AggregationAgent
from copy import deepcopy
from dataclasses import replace


class OCRAgent:
    """Agent responsible for image validation and OCR extraction."""

    def run(self, process_run, source_image, runtime_config):
        with stage_timer(
            process_run=process_run,
            source_image=source_image,
            stage="image_validation",
            runtime_config=runtime_config,
            provider=runtime_config.ocr_provider,
            model=runtime_config.ocr_model,
        ):
            validate_source_image(source_image)
        with stage_timer(
            process_run=process_run,
            source_image=source_image,
            stage="ocr",
            runtime_config=runtime_config,
            provider=runtime_config.ocr_provider,
            model=runtime_config.ocr_model,
        ) as event:
            result = extract_raw_text(source_image, runtime_config)
            event["provider"] = result["provider"]
            event["model"] = result["model"]
            event["raw_text"] = result["text"]
            event["raw_text_chars"] = len(result.get("text") or "")
            event.update(result.get("payload") or {})
            return result


class StructuringAgent:
    """Agent responsible for turning raw OCR text into structured records."""

    def run(self, process_run, source_image, raw_text, runtime_config):
        with stage_timer(
            process_run=process_run,
            source_image=source_image,
            stage="llm_structuring",
            runtime_config=runtime_config,
            provider=runtime_config.llm_provider,
            model=runtime_config.llm_model,
        ) as event:
            result = extract_structured_data(source_image, raw_text, runtime_config)
            event["provider"] = result["provider"]
            event["model"] = result["model"]
            event["records_count"] = len(result["records"])
            event.update(result.get("payload") or {})
            return result


class ValidationPersistenceAgent:
    """Agent responsible for validation and persistence of extracted records."""

    def run(self, process_run, source_image, records, runtime_config):
        if not getattr(source_image, "pk", None):
            raise ValueError(
                "ValidationPersistenceAgent requires a persisted SourceImage. "
                "Text sources must not be passed as image sources."
            )

        created_records = 0
        for structured_record in records:
            referencia = structured_record.get("referencia")
            valor = structured_record.get("valor")
            if not referencia or valor in (None, ""):
                continue

            observations, is_current_month = build_record_observations(
                structured_record.get("fecha_consignacion"),
                structured_record,
                runtime_config.extraction_criteria,
            )

            ExtractedDeposit.objects.create(
                process_run=process_run,
                source_image=source_image,
                sequence_index=source_image.sequence_index,
                fecha_consignacion=structured_record.get("fecha_consignacion") or "",
                hora_consignacion=structured_record.get("hora_consignacion") or "",
                referencia=referencia,
                valor=valor,
                is_current_month=is_current_month,
                observations=observations,
                structured_payload=structured_record,
            )
            created_records += 1
        return created_records


class ProcessingSupervisorAgent:
    """
    Orchestrator mejorado: Coordina todos los agentes especializados.

    Implementa flujo híbrido:
    1. Pipeline determinístico base
    2. Capa de multiagentes para reintentos inteligentes
    3. Agregación de resultados múltiples
    """

    def __init__(self, ocr_agent=None, structuring_agent=None, validation_agent=None):
        self.ocr_agent = ocr_agent or OCRAgent()
        self.structuring_agent = structuring_agent or StructuringAgent()
        self.validation_agent = validation_agent or ValidationPersistenceAgent()

        # Nuevos agentes de capa superior
        self.cleaning_agent = CleaningAgent()
        self.validation_agent_smart = ValidationAgent()
        self.retry_agent = RetryAgent()
        self.aggregation_agent = AggregationAgent()

    def process_image(self, process_run, source_image, runtime_config, log_callback):
        """
        Procesa una imagen con flujo híbrido + reintentos inteligentes.

        Flujo:
        1. OCR → Cleaning → Structuring → Validation
        2. Si validation falla: Retry Agent decide estrategia
        3. Agregación de múltiples intentos
        """
        # Reset agregación para esta imagen
        self.aggregation_agent.clear_history()
        self.retry_agent.reset_image_retries(source_image.id)

        attempt_number = 1
        current_config = deepcopy(runtime_config)
        final_records = []

        # Loop de reintentos
        while attempt_number <= self.retry_agent.MAX_RETRIES_PER_IMAGE:
            try:
                # === FASE 1: OCR ===
                ocr_result = self._run_ocr_phase(
                    process_run, source_image, current_config, log_callback
                )
                if not ocr_result or ocr_result.get("error"):
                    raise Exception(f"OCR failed: {ocr_result.get('error')}")

                # === FASE 2: CLEANING ===
                cleaning_result = self._run_cleaning_phase(ocr_result, log_callback)

                # === FASE 3: STRUCTURING ===
                structured_result = self._run_structuring_phase(
                    process_run,
                    source_image,
                    cleaning_result.cleaned_text,
                    current_config,
                    log_callback,
                )
                if not structured_result or structured_result.get("error"):
                    raise Exception(
                        f"Structuring failed: {structured_result.get('error')}"
                    )

                # === FASE 4: SMART VALIDATION ===
                validation_results = self._validate_records(
                    structured_result["records"], current_config
                )

                # Registrar intento en agregador
                avg_confidence = (
                    sum(r.confidence_score for r in validation_results)
                    / len(validation_results)
                    if validation_results
                    else 0.0
                )
                self.aggregation_agent.record_attempt(
                    attempt_number=attempt_number,
                    strategy_used=f"OCR:{current_config.ocr_mode}|LLM:{current_config.llm_model}",
                    ocr_text=cleaning_result.cleaned_text,
                    records=structured_result["records"],
                    confidence=avg_confidence,
                )

                # Analizar resultados
                all_valid = all(r.is_valid for r in validation_results)

                if all_valid:
                    # ✅ Validación exitosa - guardar y salir
                    log_callback(
                        process_run,
                        source_image,
                        "validation_passed",
                        current_config,
                        notes=f"All records valid (attempt {attempt_number}, confidence: {avg_confidence:.2f})",
                        raw_payload={"records_validated": len(validation_results)},
                    )
                    final_records = structured_result["records"]
                    break
                else:
                    # ❌ Validación falló - decidir reintentar
                    failed_count = sum(1 for r in validation_results if not r.is_valid)
                    log_callback(
                        process_run,
                        source_image,
                        "validation_failed",
                        current_config,
                        notes=f"Validation failed for {failed_count}/{len(validation_results)} records (attempt {attempt_number})",
                        raw_payload={
                            "failed_records": failed_count,
                            "total_records": len(validation_results),
                            "avg_confidence": avg_confidence,
                        },
                    )

                    retry_decision = self.retry_agent.decide(
                        image_id=source_image.id,
                        error_type="validation_failed",
                        validation_result=(
                            validation_results[0] if validation_results else None
                        ),
                        current_config=current_config,
                    )

                    if not retry_decision.should_retry:
                        log_callback(
                            process_run,
                            source_image,
                            "retry_decision_no_retry",
                            current_config,
                            notes=f"No retry: {retry_decision.reason}",
                            raw_payload={"strategy": retry_decision.strategy},
                        )
                        # Usar agregación para seleccionar mejor intento
                        final_records = self._aggregate_and_select_records()
                        break
                    else:
                        # Aplicar estrategia de reintentos
                        current_config = self._apply_retry_strategy(
                            current_config, retry_decision
                        )
                        log_callback(
                            process_run,
                            source_image,
                            "retry_applied",
                            current_config,
                            notes=f"Retrying with strategy: {retry_decision.strategy}",
                            raw_payload={"strategy": retry_decision.strategy.value},
                        )
                        attempt_number += 1

            except Exception as e:
                # Error durante procesamiento
                error_type = self._classify_error(str(e))
                log_callback(
                    process_run,
                    source_image,
                    f"error_{error_type}",
                    current_config,
                    notes=f"Error on attempt {attempt_number}: {str(e)}",
                    is_error=True,
                    raw_payload={"error_class": error_type},
                )

                retry_decision = self.retry_agent.decide(
                    image_id=source_image.id,
                    error_type=error_type,
                    current_config=current_config,
                )

                if (
                    not retry_decision.should_retry
                    or attempt_number >= self.retry_agent.MAX_RETRIES_PER_IMAGE
                ):
                    log_callback(
                        process_run,
                        source_image,
                        "error_final",
                        current_config,
                        notes=f"Cannot recover from {error_type}",
                        is_error=True,
                    )
                    break

                current_config = self._apply_retry_strategy(
                    current_config, retry_decision
                )
                attempt_number += 1

        # === PERSISTENCIA ===
        records_count = self._persist_records(
            process_run, source_image, final_records, runtime_config
        )

        # Actualizar estado de imagen
        source_image.ocr_status = SourceImage.OCRStatus.PROCESSED
        source_image.error_message = ""
        source_image.save(
            update_fields=[
                "ocr_status",
                "ocr_raw_text",
                "ocr_provider",
                "error_message",
                "updated_at",
            ]
        )

        # Log de agregación (auditoría)
        aggregated = self.aggregation_agent.aggregate()
        if aggregated:
            log_callback(
                process_run,
                source_image,
                "aggregation_summary",
                runtime_config,
                raw_payload={
                    "total_attempts": len(aggregated.all_attempts),
                    "consensus_records": len(aggregated.consensus_records),
                    "conflicting_records": len(aggregated.conflicting_records),
                    "aggregation_confidence": aggregated.aggregation_confidence,
                    "recommendation": aggregated.recommendation,
                },
            )

        return records_count

    def _run_ocr_phase(self, process_run, source_image, runtime_config, log_callback):
        """Fase 1: Extracción OCR."""
        try:
            with stage_timer(
                process_run=process_run,
                source_image=source_image,
                stage="image_validation",
                runtime_config=runtime_config,
                provider=runtime_config.ocr_provider,
                model=runtime_config.ocr_model,
            ):
                validate_source_image(source_image)

            with stage_timer(
                process_run=process_run,
                source_image=source_image,
                stage="ocr",
                runtime_config=runtime_config,
                provider=runtime_config.ocr_provider,
                model=runtime_config.ocr_model,
            ) as event:
                result = extract_raw_text(source_image, runtime_config)
                event["provider"] = result["provider"]
                event["model"] = result["model"]
                event["raw_text"] = result["text"]
                event["raw_text_chars"] = len(result.get("text") or "")
                event.update(result.get("payload") or {})

            return result
        except Exception as e:
            return {"error": str(e), "text": ""}

    def _run_cleaning_phase(self, ocr_result, log_callback):
        """Fase 2: Limpieza de OCR."""
        raw_text = ocr_result.get("text", "")
        cleaning_result = self.cleaning_agent.run(raw_text, None)
        return cleaning_result

    def _run_structuring_phase(
        self, process_run, source_image, text, runtime_config, log_callback
    ):
        """Fase 3: Extracción LLM."""
        try:
            with stage_timer(
                process_run=process_run,
                source_image=source_image,
                stage="llm_structuring",
                runtime_config=runtime_config,
                provider=runtime_config.llm_provider,
                model=runtime_config.llm_model,
            ) as event:
                result = extract_structured_data(source_image, text, runtime_config)
                event["provider"] = result["provider"]
                event["model"] = result["model"]
                event["records_count"] = len(result["records"])
                event.update(result.get("payload") or {})
            return result
        except Exception as e:
            return {"error": str(e), "records": []}

    def _validate_records(self, records, runtime_config):
        """Fase 4: Validación inteligente."""
        validation_results = []
        for record in records:
            result = self.validation_agent_smart.validate_record(record)
            validation_results.append(result)
        return validation_results

    def _apply_retry_strategy(self, config, retry_decision):
        """Aplica la estrategia de reintentos a la configuración."""
        config_copy = deepcopy(config)

        if retry_decision.strategy == RetryStrategy.CHANGE_OCR_MODE:
            if retry_decision.next_ocr_mode:
                config_copy = replace(
                    config_copy, ocr_mode=retry_decision.next_ocr_mode
                )
        elif retry_decision.strategy == RetryStrategy.CHANGE_LLM_MODEL:
            if retry_decision.next_llm_model:
                config_copy = replace(
                    config_copy, llm_model=retry_decision.next_llm_model
                )
        elif retry_decision.strategy == RetryStrategy.INCREASE_TIMEOUT:
            next_timeout = int(
                config_copy.request_timeout_seconds
                * retry_decision.next_timeout_multiplier
            )
            config_copy = replace(config_copy, request_timeout_seconds=next_timeout)

        return config_copy

    def _aggregate_and_select_records(self):
        """Usa agregación para seleccionar los mejores registros."""
        aggregated = self.aggregation_agent.aggregate()
        if aggregated:
            if aggregated.recommendation == "accept":
                return aggregated.consensus_records
            elif aggregated.recommendation == "review":
                # Incluir consenso y mejor intento
                return aggregated.best_attempt.records
            else:
                # Usar mejor intento como fallback
                return (
                    aggregated.best_attempt.records if aggregated.best_attempt else []
                )
        return []

    def _persist_records(self, process_run, source_image, records, runtime_config):
        """Persiste registros validados en BD."""
        records_count = self.validation_agent.run(
            process_run, source_image, records, runtime_config
        )
        return records_count

    def _classify_error(self, error_message: str) -> str:
        """Clasifica el tipo de error."""
        error_lower = error_message.lower()
        if "ocr" in error_lower or "image" in error_lower:
            return "ocr_failed"
        elif "timeout" in error_lower:
            return "timeout"
        elif "llm" in error_lower or "extract" in error_lower:
            return "extraction_failed"
        else:
            return "unknown"
