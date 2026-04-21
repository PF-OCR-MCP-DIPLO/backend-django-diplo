from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _default_message_for_status(status_code: int) -> str:
    if status_code == status.HTTP_400_BAD_REQUEST:
        return "Solicitud invalida."
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "No autenticado."
    if status_code == status.HTTP_403_FORBIDDEN:
        return "No autorizado."
    if status_code == status.HTTP_404_NOT_FOUND:
        return "Recurso no encontrado."
    if status_code == status.HTTP_409_CONFLICT:
        return "Conflicto de estado."
    if status_code >= 500:
        return "Error interno del servidor."
    return f"Error {status_code}"


def _code_for_exception(exc: Exception, status_code: int) -> str:
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    if isinstance(exc, (exceptions.NotFound, Http404)):
        return "not_found"
    if isinstance(exc, (exceptions.PermissionDenied, DjangoPermissionDenied)):
        return "forbidden"
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        return "unauthorized"
    if isinstance(exc, exceptions.ParseError):
        return "parse_error"
    if status_code == status.HTTP_409_CONFLICT:
        return "conflict"
    if status_code >= 500:
        return "internal_error"
    return "error"


def _extract_message_and_details(
    data: Any, fallback_message: str
) -> tuple[str, Any | None]:
    # DRF uses:
    # - {"detail": "..."} for many errors
    # - {"field": ["..."]} for validation errors
    if isinstance(data, dict) and "detail" in data and isinstance(data["detail"], str):
        return data["detail"], None
    if isinstance(data, str):
        return data, None
    if isinstance(data, dict):
        return fallback_message, data
    if isinstance(data, list):
        return fallback_message, data
    return fallback_message, None


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    status_code = response.status_code
    code = _code_for_exception(exc, status_code)
    fallback_message = _default_message_for_status(status_code)
    message, details = _extract_message_and_details(response.data, fallback_message)

    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details

    response.data = payload
    return response
