"""Cliente HTTP interno del servidor MCP hacia la API Django."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


class BackendApiError(RuntimeError):
    """Error controlado devuelto por la API backend al operar desde MCP."""

    def __init__(self, status_code: int, detail: str, payload: Any | None = None):
        self.status_code = status_code
        self.detail = detail
        self.payload = payload
        super().__init__(f"Backend API error {status_code}: {detail}")


class BackendApiClient:
    """Encapsula las llamadas HTTP que el servidor MCP delega al backend."""

    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        """Inicializa cliente HTTP con parámetros overrideables por entorno.

        Variables de entorno:
            MCP_BACKEND_BASE_URL: URL base de la API (default localhost).
            MCP_BACKEND_API_TOKEN: API key opcional para endpoints protegidos.
            MCP_BACKEND_TIMEOUT: timeout base de requests (segundos).
        """
        env_base = os.getenv("MCP_BACKEND_BASE_URL", "http://127.0.0.1:8000/api")
        self.base_url = (base_url or env_base).rstrip("/")
        self.api_token = api_token or os.getenv("MCP_BACKEND_API_TOKEN", "")
        self.timeout = float(os.getenv("MCP_BACKEND_TIMEOUT", "60"))

    def _headers(self) -> dict[str, str]:
        """Construye headers comunes incluyendo `X-API-Key` cuando aplica."""
        headers: dict[str, str] = {}
        if self.api_token:
            headers["X-API-Key"] = self.api_token
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Ejecuta HTTP con timeout y errores normalizados para MCP."""
        request_headers = {**self._headers(), **(headers or {})}
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=request_headers,
                timeout=self.timeout if timeout is None else timeout,
                **kwargs,
            )
        except requests.Timeout as exc:
            raise BackendApiError(504, "Backend request timed out") from exc
        except requests.RequestException as exc:
            raise BackendApiError(502, "Backend request failed") from exc
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> Any:
        """Normaliza éxito/error HTTP al contrato interno del cliente.

        Raises:
            BackendApiError: para respuestas no exitosas con detalle serializado.
        """
        if response.ok:
            if response.content:
                try:
                    return response.json()
                except ValueError:
                    return {}
            return {}
        payload: Any | None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        detail = "Unknown error"
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                detail = str(
                    error_payload.get("message")
                    or error_payload.get("detail")
                    or error_payload
                )
            else:
                detail = str(payload.get("detail") or payload.get("message") or payload)
        elif payload is None:
            detail = response.text or detail
        raise BackendApiError(response.status_code, detail, payload)

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health/")

    def upload_document(self, file_path: str) -> dict[str, Any]:
        """Envía un `.docx` a la API backend vía multipart/form-data."""
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
            return self._request("POST", "/documents/upload/", files=files)

    def process_job(self, job_id: int, *, force: bool = False) -> dict[str, Any]:
        """Dispara procesamiento de job con timeout extendido por operación pesada."""
        return self._request(
            "POST",
            f"/jobs/{job_id}/process/",
            params={"force": "true"} if force else None,
            timeout=max(self.timeout, 600),
        )

    def reprocess_failed_sources(self, job_id: int) -> dict[str, Any]:
        """Solicita reproceso de fuentes fallidas para un job específico."""
        return self._request(
            "POST",
            f"/jobs/{job_id}/reprocess-failed/",
            timeout=max(self.timeout, 600),
        )

    def reprocess_source_image(
        self,
        job_id: int,
        source_image_id: int,
    ) -> dict[str, Any]:
        """Solicita reproceso puntual de una imagen fuente."""
        return self._request(
            "POST",
            f"/jobs/{job_id}/source-images/{source_image_id}/reprocess/",
            timeout=max(self.timeout, 600),
        )

    def get_job_status(self, job_id: int) -> dict[str, Any]:
        return self._request("GET", f"/jobs/{job_id}/")

    def list_jobs(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/jobs/")
        return payload if isinstance(payload, list) else []

    def get_job_logs(self, job_id: int) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/jobs/{job_id}/logs/")
        return payload if isinstance(payload, list) else []

    def export_job_excel(self, job_id: int) -> dict[str, Any]:
        return self._request("POST", f"/jobs/{job_id}/export/")

    def get_processing_settings(self) -> dict[str, Any]:
        return self._request("GET", "/processing/settings/")

    def get_processing_settings_options(self) -> dict[str, Any]:
        return self._request("GET", "/processing/settings/options/")

    def assistant_chat(
        self,
        *,
        messages: list[dict[str, str]],
        job_id: int | None = None,
        errors: int = 0,
        query_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ejecuta el endpoint de asistente con contrato compatible REST."""
        payload: dict[str, Any] = {
            "messages": messages,
            "errors": errors,
            "query_context": query_context or {},
        }
        if job_id is not None:
            payload["job_id"] = job_id
        return self._request(
            "POST",
            "/assistant/chat/",
            headers={"Content-Type": "application/json"},
            json=payload,
        )

    def update_processing_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH",
            "/processing/settings/",
            headers={"Content-Type": "application/json"},
            json=updates,
        )
