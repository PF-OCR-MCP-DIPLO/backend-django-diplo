from django.test import SimpleTestCase

from apps.common.utils.currency import smart_parse_currency
from apps.extraction.schemas import ConsignacionBasica
from apps.extraction.services.validators import build_record_observations
from apps.processing.services.extraction_criteria import default_extraction_criteria


class CurrencyTests(SimpleTestCase):
    def test_smart_parse_currency(self):
        self.assertEqual(smart_parse_currency("1.200,50"), 1200.5)
        self.assertEqual(smart_parse_currency("$1,200.50"), 1200.5)
        self.assertEqual(smart_parse_currency("70000"), 70000.0)
        self.assertIsNone(smart_parse_currency(""))
        self.assertIsNone(smart_parse_currency(None))

    def test_smart_parse_currency_regional_formats(self):
        cases = {
            "50.000,00": 50000.0,
            "50,000.00": 50000.0,
            "$50.000,00": 50000.0,
            "COP 50.000,00": 50000.0,
            "50000": 50000.0,
            "50 000,00": 50000.0,
            "50.000": 50000.0,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(smart_parse_currency(raw), expected)


class ExtractionSchemaTests(SimpleTestCase):
    def test_valid_record(self):
        record = ConsignacionBasica(
            fecha_consignacion="15/04/2026",
            hora_consignacion="09:30",
            referencia="ABC123",
            valor="50.000,00",
        )
        self.assertEqual(record.valor, 50000.0)

    def test_valid_record_accepts_regional_currency_formats(self):
        values = [
            "50.000,00",
            "50,000.00",
            "$50.000,00",
            "COP 50.000,00",
            "50000",
            "50 000,00",
        ]
        for raw in values:
            with self.subTest(raw=raw):
                record = ConsignacionBasica(
                    fecha_consignacion="15/04/2026",
                    hora_consignacion="09:30",
                    referencia="ABC123",
                    valor=raw,
                )
                self.assertEqual(record.valor, 50000.0)

    def test_invalid_or_negative_valor_rejected(self):
        for raw in ["0", 0, "-50.000,00", "-1"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    ConsignacionBasica(
                        fecha_consignacion="15/04/2026",
                        hora_consignacion="09:30",
                        referencia="ABC123",
                        valor=raw,
                    )

    def test_invalid_reference_raises(self):
        with self.assertRaises(ValueError):
            ConsignacionBasica(
                fecha_consignacion="15/04/2026",
                hora_consignacion="09:30",
                referencia="ok",
                valor="50000",
            )

    def test_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            ConsignacionBasica(
                fecha_consignacion="2026-04-15",
                hora_consignacion="09:30",
                referencia="ABC123",
                valor="50000",
            )

    def test_build_record_observations_uses_extraction_criteria(self):
        criteria = default_extraction_criteria()
        criteria["fields"].append(
            {
                "key": "referencia",
                "label": "Referencia exacta",
                "type": "text",
                "required": True,
                "enabled": True,
                "expectedValue": "REF001",
                "validationRules": [
                    {
                        "kind": "equals",
                        "value": "REF001",
                        "message": "La referencia debe ser REF001",
                    }
                ],
                "helpText": "",
                "order": 5,
            }
        )
        observations, is_current_month = build_record_observations(
            "15/04/2026",
            {
                "fecha_consignacion": "15/04/2026",
                "hora_consignacion": "09:30",
                "referencia": "REF999",
                "valor": 50000.0,
            },
            criteria,
            4,
            2026,
        )
        self.assertTrue(is_current_month)
        self.assertIn("La referencia debe ser REF001", observations)

    def test_build_record_observations_uses_configured_period(self):
        observations, is_current_month = build_record_observations(
            "15/03/2026",
            {"fecha_consignacion": "15/03/2026"},
            default_extraction_criteria(),
            4,
            2026,
        )

        self.assertFalse(is_current_month)
        self.assertIn("Fecha fuera del periodo valido configurado", observations)

    def test_build_record_observations_does_not_depend_on_system_month(self):
        observations, is_current_month = build_record_observations(
            "15/04/2026",
            {"fecha_consignacion": "15/04/2026"},
            default_extraction_criteria(),
            4,
            2026,
        )

        self.assertTrue(is_current_month)
        self.assertNotIn("Fecha fuera del periodo valido configurado", observations)

    def test_hora_consignacion_normalizes_12h_to_24h(self):
        cases = {
            "2:00 pm": "14:00",
            "2:00 p. m.": "14:00",
            "02:00 PM": "14:00",
            "11:49 a. m.": "11:49",
            "12:00 am": "00:00",
            "12:00 a. m.": "00:00",
            "12:00 pm": "12:00",
            "12:00 p. m.": "12:00",
            "05:52": "05:52",
            "14:30": "14:30",
            "10:13:03": "10:13",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                record = ConsignacionBasica(
                    fecha_consignacion="15/04/2026",
                    hora_consignacion=raw,
                    referencia="ABC123",
                    valor="50.000,00",
                )
                self.assertEqual(record.hora_consignacion, expected)
