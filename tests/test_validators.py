from django.test import SimpleTestCase

from apps.common.utils.currency import smart_parse_currency
from apps.extraction.schemas import ConsignacionBasica


class CurrencyTests(SimpleTestCase):
    def test_smart_parse_currency(self):
        self.assertEqual(smart_parse_currency("1.200,50"), 1200.5)
        self.assertEqual(smart_parse_currency("$1,200.50"), 1200.5)
        self.assertEqual(smart_parse_currency("70000"), 70000.0)


class ExtractionSchemaTests(SimpleTestCase):
    def test_valid_record(self):
        record = ConsignacionBasica(
            fecha_consignacion="15/04/2026",
            hora_consignacion="09:30",
            referencia="ABC123",
            valor="50.000,00",
        )
        self.assertEqual(record.valor, 50000.0)

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
