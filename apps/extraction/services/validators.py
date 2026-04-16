from datetime import datetime

from django.utils import timezone


def build_record_observations(fecha_consignacion):
    observations = []
    if not fecha_consignacion:
        observations.append("Fecha no identificada")
        return observations, None
    try:
        extracted_date = datetime.strptime(fecha_consignacion, "%d/%m/%Y").date()
    except ValueError:
        observations.append("Fecha invalida")
        return observations, None
    today = timezone.localdate()
    is_current_month = (
        extracted_date.month == today.month and extracted_date.year == today.year
    )
    if not is_current_month:
        observations.append("Fecha fuera del mes actual")
    return observations, is_current_month
