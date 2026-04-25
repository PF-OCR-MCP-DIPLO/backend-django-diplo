from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


class BackendApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str, payload: Any | None = None):
        self.status_code = status_code
        self.detail = detail
        self.payload = payload
        super().__init__(f"Backend API error {status_code}: {detail}")


class BackendApiClient:
    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        env_base = os.getenv("MCP_BACKEND_BASE_URL", "http://127.0.0.1:8000/api")
        self.base_url = (base_url or env_base).rstrip("/")
        self.api_token = api_token or os.getenv("MCP_BACKEND_API_TOKEN", "")
        self.timeout = float(os.getenv("MCP_BACKEND_TIMEOUT", "60"))

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_token:
            headers["X-API-Key"] = self.api_token
        return headers

    def _handle_response(self, response: requests.Response) -> Any:
        if response.ok:
            if response.content:
                return response.json()
            return {}
        payload: Any | None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        detail = "Unknown error"
        if isinstance(payload, dict):
            detail = str(payload.get("detail") or payload)
        elif payload is None:
            detail = response.text or detail
        raise BackendApiError(response.status_code, detail, payload)

    def get_health(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/health/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def upload_document(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"File not found: {file_path}")
        if path.suffix.lower() != ".docx":
            raise ValueError("Only .docx files are supported")
        with path.open("rb") as file_obj:
            files = {
                "file": (
                    path.name,
                    file_obj,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
            response = requests.post(
                f"{self.base_url}/documents/upload/",
                headers=self._headers(),
                files=files,
                timeout=self.timeout,
            )
        return self._handle_response(response)

    def process_job(self, job_id: int) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/jobs/{job_id}/process/",
            headers=self._headers(),
            timeout=max(self.timeout, 600),
        )
        return self._handle_response(response)

    def get_job_status(self, job_id: int) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/jobs/{job_id}/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def list_jobs(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/jobs/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        payload = self._handle_response(response)
        return payload if isinstance(payload, list) else []

    def get_job_logs(self, job_id: int) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/jobs/{job_id}/logs/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        payload = self._handle_response(response)
        return payload if isinstance(payload, list) else []

    def export_job_excel(self, job_id: int) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/jobs/{job_id}/export/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def get_processing_settings(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/processing/settings/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def get_processing_settings_options(self) -> dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/processing/settings/options/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def assistant_chat(
        self,
        *,
        messages: list[dict[str, str]],
        job_id: int | None = None,
        errors: int = 0,
        query_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "errors": errors,
            "query_context": query_context or {},
        }
        if job_id is not None:
            payload["job_id"] = job_id
        response = requests.post(
            f"{self.base_url}/assistant/chat/",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        return self._handle_response(response)

    def update_processing_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        response = requests.patch(
            f"{self.base_url}/processing/settings/",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=updates,
            timeout=self.timeout,
        )
        return self._handle_response(response)
