"""Utilidades para normalizar el formato de error de la API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework.response import Response

from apps.common.middleware.request_id import get_current_request_id


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    details: Any | None = None


def api_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> Response:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    request_id = get_current_request_id()
    if request_id:
        payload["request_id"] = request_id
    return Response(payload, status=status_code)
