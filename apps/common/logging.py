"""Utilidades de logging transversales del backend."""

from __future__ import annotations

from apps.common.middleware.request_id import get_current_request_id


class RequestIdLogFilter:
    """Filtro que inyecta `request_id` en cada registro de log.

    Permite correlacionar eventos de aplicación con una request HTTP específica.
    Si no existe contexto activo, usa `-` para evitar fallas de formateo.
    """

    def filter(self, record):
        record.request_id = get_current_request_id() or "-"
        return True
