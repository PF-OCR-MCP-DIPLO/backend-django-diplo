from __future__ import annotations

from apps.common.middleware.request_id import get_current_request_id


class RequestIdLogFilter:
    def filter(self, record):
        record.request_id = get_current_request_id() or "-"
        return True

