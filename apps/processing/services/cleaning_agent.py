"""
Cleaning Agent: Normaliza y corrige texto OCR.

Responsable de:
- Corregir errores comunes del OCR (caracteres mal interpretados)
- Normalizar formatos (moneda, fechas, referencias)
- Validar patrones esperados
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class CleaningResult:
    """Resultado de la limpieza de OCR."""
    original_text: str
    cleaned_text: str
    corrections_applied: int
    confidence_score: float
    issues_found: list


class CleaningAgent:
    """Agente especializado en limpieza y normalización de OCR."""

    # Patrones comunes de errores OCR
    COMMON_REPLACEMENTS = {
        # Caracteres mal interpretados como números
        'O': '0', 'l': '1', 'I': '1', 'Z': '2', 'S': '5',
        # Moneda
        '$': '$', '€': '€', '¢': '¢',
    }

    CURRENCY_PATTERNS = [
        (r'[$€]\s*(\d+)', r'$\1'),  # Normalizar espacios después de símbolo
        (r'(\d+)\s*([.,])\s*(\d{2,3})', r'\1\2\3'),  # Normalizar miles/decimales
    ]

    DATE_PATTERNS = [
        (r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', r'\1/\2/\3'),  # DD/MM/YYYY
        (r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})', r'\1/\2/20\3'),  # DD/MM/YY → DD/MM/YYYY
    ]

    TIME_PATTERNS = [
        (r'(\d{1,2}):(\d{2})', r'\1:\2'),  # HH:MM
    ]

    REFERENCE_PATTERNS = [
        (r'\s+', ' '),  # Múltiples espacios → uno
        (r'[^\w\s/-]', ''),  # Caracteres especiales no alfanuméricos
    ]

    def run(self, raw_text: str, runtime_config) -> CleaningResult:
        """
        Limpia el texto OCR.
        
        Args:
            raw_text: Texto sin procesar del OCR
            runtime_config: Configuración runtime con criterios
            
        Returns:
            CleaningResult con texto limpiado y estadísticas
        """
        if not raw_text or not raw_text.strip():
            return CleaningResult(
                original_text=raw_text,
                cleaned_text="",
                corrections_applied=0,
                confidence_score=0.0,
                issues_found=["Empty OCR text"],
            )

        original_length = len(raw_text)
        cleaned_text = raw_text
        corrections = 0
        issues = []

        # Fase 1: Normalizar espacios y caracteres
        cleaned_text = self._normalize_whitespace(cleaned_text)

        # Fase 2: Corregir moneda
        cleaned_text, currency_fixes = self._normalize_currency(cleaned_text)
        corrections += currency_fixes

        # Fase 3: Normalizar fechas
        cleaned_text, date_fixes = self._normalize_dates(cleaned_text)
        corrections += date_fixes

        # Fase 4: Normalizar horas
        cleaned_text, time_fixes = self._normalize_times(cleaned_text)
        corrections += time_fixes

        # Fase 5: Limpiar referencias
        cleaned_text, ref_fixes = self._normalize_references(cleaned_text)
        corrections += ref_fixes

        # Calcular confianza
        final_length = len(cleaned_text)
        confidence = self._calculate_confidence(
            original_length, final_length, corrections, cleaned_text
        )

        # Detectar problemas potenciales
        if final_length == 0:
            issues.append("Text completely cleaned (empty result)")
        elif final_length < 10:
            issues.append("Very short cleaned text (< 10 chars)")
        elif final_length < original_length * 0.5:
            issues.append(f"Significant text loss: {original_length} → {final_length} chars")

        return CleaningResult(
            original_text=raw_text,
            cleaned_text=cleaned_text,
            corrections_applied=corrections,
            confidence_score=confidence,
            issues_found=issues,
        )

    def _normalize_whitespace(self, text: str) -> str:
        """Normaliza espacios y saltos de línea."""
        # Múltiples espacios → uno
        text = re.sub(r' +', ' ', text)
        # Saltos de línea múltiples → uno
        text = re.sub(r'\n+', '\n', text)
        # Espacios alrededor de saltos de línea
        text = re.sub(r' *\n *', '\n', text)
        return text.strip()

    def _normalize_currency(self, text: str) -> tuple[str, int]:
        """Normaliza formatos de moneda."""
        fixes = 0
        for pattern, replacement in self.CURRENCY_PATTERNS:
            matches = len(re.findall(pattern, text))
            text = re.sub(pattern, replacement, text)
            fixes += matches
        return text, fixes

    def _normalize_dates(self, text: str) -> tuple[str, int]:
        """Normaliza fechas a DD/MM/YYYY."""
        fixes = 0
        for pattern, replacement in self.DATE_PATTERNS:
            matches = len(re.findall(pattern, text))
            text = re.sub(pattern, replacement, text)
            fixes += matches
        return text, fixes

    def _normalize_times(self, text: str) -> tuple[str, int]:
        """Normaliza horas a HH:MM."""
        fixes = 0
        for pattern, replacement in self.TIME_PATTERNS:
            matches = len(re.findall(pattern, text))
            text = re.sub(pattern, replacement, text)
            fixes += matches
        return text, fixes

    def _normalize_references(self, text: str) -> tuple[str, int]:
        """Limpia y normaliza referencias."""
        fixes = 0
        original = text
        for pattern, replacement in self.REFERENCE_PATTERNS:
            text = re.sub(pattern, replacement, text)
        fixes = 1 if text != original else 0
        return text, fixes

    def _calculate_confidence(
        self, original_len: int, final_len: int, corrections: int, text: str
    ) -> float:
        """
        Calcula puntaje de confianza de la limpieza.
        
        Factores:
        - Conservación de longitud (no debería perder más del 60%)
        - Número de correcciones (más correcciones = menos confianza)
        - Presencia de patrones esperados (moneda, fecha, referencia)
        """
        score = 1.0

        # Penalizar pérdida significativa de texto
        if original_len > 0:
            retention = final_len / original_len
            if retention < 0.4:
                score -= 0.3
            elif retention < 0.7:
                score -= 0.1

        # Penalizar muchas correcciones (posible sobre-limpieza)
        if corrections > 20:
            score -= 0.2
        elif corrections > 10:
            score -= 0.1

        # Bonus por patrones detectados
        patterns_found = 0
        if re.search(r'\$\d+', text):
            patterns_found += 1  # Moneda
        if re.search(r'\d{1,2}/\d{1,2}/\d{4}', text):
            patterns_found += 1  # Fecha
        if re.search(r'\d{1,2}:\d{2}', text):
            patterns_found += 1  # Hora

        score += min(0.2, patterns_found * 0.05)

        return max(0.0, min(1.0, score))
