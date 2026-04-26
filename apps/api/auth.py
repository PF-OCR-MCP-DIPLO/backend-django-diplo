"""Permisos de acceso basados en API key compartida."""

from __future__ import annotations

import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


def api_key_required() -> bool:
    expected = getattr(settings, "API_KEY", "") or ""
    if expected:
        return True
    return not bool(getattr(settings, "ALLOW_OPEN_API_FOR_DEV", False))


class ApiKeyPermission(BasePermission):
    header_name = "HTTP_X_API_KEY"
    message = "Missing or invalid API key."

    def has_permission(self, request, view):
        expected = getattr(settings, "API_KEY", "") or ""
        if not api_key_required():
            return True
        if not expected:
            return False
        provided = request.META.get(self.header_name, "") or ""
        return secrets.compare_digest(provided, expected)
