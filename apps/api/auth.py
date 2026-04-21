from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission


class ApiKeyPermission(BasePermission):
    """
    Minimal API security for academic/pro demos.

    If `API_KEY` is not configured, the API stays open (DX-friendly for local dev/tests).
    If configured, requires `X-API-Key: <key>` header.
    """

    header_name = "HTTP_X_API_KEY"

    def has_permission(self, request, view):
        expected = getattr(settings, "API_KEY", "") or ""
        if not expected:
            return True
        provided = request.META.get(self.header_name, "") or ""
        return provided == expected

