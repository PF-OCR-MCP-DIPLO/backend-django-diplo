"""
Validation Agent: Valida coherencia y confiabilidad de registros extraídos.

Responsable de:
- Validar que los campos extraídos tengan sentido
- Calcular puntaje de confianza
- Detectar anomalías
- Decidir si se acepta, rechaza o requiere revisión
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
import re
from typing import Optional


@dataclass
class ValidationIssue:
    """Un problema encontrado en la validación."""
    field: str
    issue: str
    severity: str  # "critical", "warning", "info"
    value: Optional[str] = None


@dataclass
class ValidationResult:
    """Resultado de la validación de un registro."""
    is_valid: bool
    confidence_score: float  # 0.0 a 1.0
    needs_review: bool
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    
    def __post_init__(self):
        """Determina si necesita revisión basado en confianza."""
        if self.confidence_score < 0.6:
            self.needs_review = True


class ValidationAgent:
    """Agente especializado en validación de registros extraídos."""

    # Límites de validez para depósitos
    MIN_AMOUNT = Decimal('0.01')
    MAX_AMOUNT = Decimal('999999999.99')
    
    # Campos requeridos
    REQUIRED_FIELDS = {'referencia', 'valor'}
    
    # Patrones validación
    REFERENCE_PATTERN = re.compile(r'^[A-Z0-9\-/ ]{3,}$', re.IGNORECASE)
    DATE_PATTERN = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
    TIME_PATTERN = re.compile(r'^\d{1,2}:\d{2}$')

    def __init__(self, extraction_criteria: dict = None):
        """
        Inicializa el agente de validación.
        
        Args:
            extraction_criteria: Criterios personalizados de extracción
        """
        self.extraction_criteria = extraction_criteria or {}

    def validate_record(self, record: dict) -> ValidationResult:
        """
        Valida un registro extraído.
        
        Args:
            record: Diccionario con campos extraídos
            
        Returns:
            ValidationResult con resultado y detalles
        """
        issues = []
        confidence = 1.0

        # Fase 1: Validar campos requeridos
        missing_fields = self.REQUIRED_FIELDS - set(record.keys())
        for field_name in missing_fields:
            issues.append(ValidationIssue(
                field=field_name,
                issue=f"Missing required field: {field_name}",
                severity="critical",
            ))
            confidence -= 0.3

        # Si faltan campos críticos, fallar inmediatamente
        if 'referencia' not in record or 'valor' not in record:
            return ValidationResult(
                is_valid=False,
                confidence_score=max(0.0, confidence),
                needs_review=True,
                validation_issues=issues,
            )

        # Fase 2: Validar referencia
        ref_issues, ref_confidence = self._validate_referencia(record.get('referencia', ''))
        issues.extend(ref_issues)
        confidence *= ref_confidence

        # Fase 3: Validar monto
        amount_issues, amount_confidence = self._validate_valor(record.get('valor'))
        issues.extend(amount_issues)
        confidence *= amount_confidence

        # Fase 4: Validar fecha (opcional pero recomendado)
        if 'fecha_consignacion' in record:
            date_issues, date_confidence = self._validate_fecha(record['fecha_consignacion'])
            issues.extend(date_issues)
            confidence *= date_confidence

        # Fase 5: Validar hora (opcional)
        if 'hora_consignacion' in record:
            time_issues, time_confidence = self._validate_hora(record['hora_consignacion'])
            issues.extend(time_issues)
            confidence *= time_confidence

        # Fase 6: Validaciones cross-field
        cross_issues, cross_confidence = self._validate_cross_fields(record)
        issues.extend(cross_issues)
        confidence *= cross_confidence

        # Determinar validez
        critical_issues = [i for i in issues if i.severity == 'critical']
        is_valid = len(critical_issues) == 0 and confidence > 0.3

        return ValidationResult(
            is_valid=is_valid,
            confidence_score=max(0.0, min(1.0, confidence)),
            needs_review=confidence < 0.6 or len(issues) > 0,
            validation_issues=issues,
        )

    def _validate_referencia(self, referencia: str) -> tuple[list, float]:
        """Valida el campo referencia."""
        issues = []
        confidence = 1.0

        if not referencia:
            issues.append(ValidationIssue(
                field='referencia',
                issue='Reference is empty',
                severity='critical',
            ))
            return issues, 0.0

        if len(referencia) < 3:
            issues.append(ValidationIssue(
                field='referencia',
                issue=f'Reference too short (len={len(referencia)})',
                severity='warning',
                value=referencia,
            ))
            confidence -= 0.2

        if len(referencia) > 100:
            issues.append(ValidationIssue(
                field='referencia',
                issue=f'Reference too long (len={len(referencia)})',
                severity='warning',
                value=f'{referencia[:50]}...',
            ))
            confidence -= 0.15

        # Validar caracteres esperados
        if not self.REFERENCE_PATTERN.match(referencia):
            issues.append(ValidationIssue(
                field='referencia',
                issue='Reference contains unexpected characters',
                severity='warning',
                value=referencia,
            ))
            confidence -= 0.1

        return issues, max(0.3, confidence)

    def _validate_valor(self, valor) -> tuple[list, float]:
        """Valida el monto."""
        issues = []
        confidence = 1.0

        if valor is None or valor == '':
            issues.append(ValidationIssue(
                field='valor',
                issue='Amount is empty',
                severity='critical',
            ))
            return issues, 0.0

        # Convertir a Decimal
        try:
            if isinstance(valor, str):
                # Limpiar símbolo de moneda y mil separadores
                valor_str = valor.replace('$', '').replace(',', '').strip()
                amount = Decimal(valor_str)
            else:
                amount = Decimal(str(valor))
        except:
            issues.append(ValidationIssue(
                field='valor',
                issue=f'Invalid amount format: {valor}',
                severity='critical',
                value=str(valor),
            ))
            return issues, 0.0

        # Validar rango
        if amount <= 0:
            issues.append(ValidationIssue(
                field='valor',
                issue=f'Amount must be positive: {amount}',
                severity='critical',
                value=str(amount),
            ))
            confidence -= 0.5

        if amount < self.MIN_AMOUNT:
            issues.append(ValidationIssue(
                field='valor',
                issue=f'Amount below minimum ({self.MIN_AMOUNT}): {amount}',
                severity='warning',
                value=str(amount),
            ))
            confidence -= 0.2

        if amount > self.MAX_AMOUNT:
            issues.append(ValidationIssue(
                field='valor',
                issue=f'Amount exceeds maximum ({self.MAX_AMOUNT}): {amount}',
                severity='warning',
                value=str(amount),
            ))
            confidence -= 0.2

        # Bonus si el monto es "normal"
        if Decimal('100') <= amount <= Decimal('10000000'):
            confidence += 0.1

        return issues, max(0.3, confidence)

    def _validate_fecha(self, fecha: str) -> tuple[list, float]:
        """Valida la fecha."""
        issues = []
        confidence = 1.0

        if not fecha or not fecha.strip():
            # Fecha opcional, pero si existe debe ser válida
            return issues, confidence

        if not self.DATE_PATTERN.match(fecha):
            issues.append(ValidationIssue(
                field='fecha_consignacion',
                issue=f'Invalid date format (expected DD/MM/YYYY): {fecha}',
                severity='warning',
                value=fecha,
            ))
            return issues, 0.7

        # Validar que sea una fecha real
        try:
            day, month, year = fecha.split('/')
            date_obj = datetime(int(year), int(month), int(day))
            
            # Advertencia si es fecha futura
            if date_obj > datetime.now():
                issues.append(ValidationIssue(
                    field='fecha_consignacion',
                    issue='Date is in the future',
                    severity='warning',
                    value=fecha,
                ))
                confidence -= 0.15

            # Advertencia si es muy antigua (> 2 años)
            if datetime.now() - date_obj > timedelta(days=730):
                issues.append(ValidationIssue(
                    field='fecha_consignacion',
                    issue='Date is more than 2 years old',
                    severity='info',
                    value=fecha,
                ))
                confidence -= 0.05

        except ValueError:
            issues.append(ValidationIssue(
                field='fecha_consignacion',
                issue=f'Invalid date value: {fecha}',
                severity='warning',
                value=fecha,
            ))
            return issues, 0.7

        return issues, max(0.5, confidence)

    def _validate_hora(self, hora: str) -> tuple[list, float]:
        """Valida la hora."""
        issues = []
        confidence = 1.0

        if not hora or not hora.strip():
            return issues, confidence

        if not self.TIME_PATTERN.match(hora):
            issues.append(ValidationIssue(
                field='hora_consignacion',
                issue=f'Invalid time format (expected HH:MM): {hora}',
                severity='info',
                value=hora,
            ))
            return issues, 0.8

        # Validar rango
        try:
            hh, mm = hora.split(':')
            hour = int(hh)
            minute = int(mm)
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError
        except:
            issues.append(ValidationIssue(
                field='hora_consignacion',
                issue=f'Invalid time value: {hora}',
                severity='info',
                value=hora,
            ))
            return issues, 0.8

        return issues, confidence

    def _validate_cross_fields(self, record: dict) -> tuple[list, float]:
        """Valida relaciones entre campos."""
        issues = []
        confidence = 1.0

        # Si hay fecha, verificar que no sea del futuro
        if 'fecha_consignacion' in record and record['fecha_consignacion']:
            try:
                day, month, year = record['fecha_consignacion'].split('/')
                date_obj = datetime(int(year), int(month), int(day))
                if date_obj > datetime.now() + timedelta(days=1):  # Permitir 1 día de margen
                    confidence -= 0.1
            except:
                pass

        # Sanidad: referencia y monto juntos
        if 'referencia' in record and 'valor' in record:
            # Si ambos existen, asumir que es un buen registro
            confidence += 0.1

        return issues, max(0.3, confidence)
