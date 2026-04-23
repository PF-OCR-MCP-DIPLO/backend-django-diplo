from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_current_request_id() -> str | None:
    return _request_id_ctx.get()


class RequestIdMiddleware:
    header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.request_id = request_id
        token = _request_id_ctx.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id_ctx.reset(token)
        try:
            response[self.header_name] = request_id
        except Exception:
            pass
        return response
