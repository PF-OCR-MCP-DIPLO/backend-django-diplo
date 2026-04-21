from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework.response import Response


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
    return Response(payload, status=status_code)
