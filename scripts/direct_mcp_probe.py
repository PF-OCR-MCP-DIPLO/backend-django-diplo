"""Prueba directa de herramientas MCP sin pasar por el modelo conversacional."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")

import django

django.setup()

from apps.processing.models import ProcessRun
from mcp_server import server


def _print_json(label: str, raw_output: str) -> dict:
    payload = json.loads(raw_output)
    print(f"{label}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return payload


def main() -> int:
    candidates = [
        Path("/home/gebert/documentos/CONSIGNACIONES MARZO 2026.docx"),
        ROOT / "CONSIGNACIONES MARZO 2026.docx",
        Path("/home/gebert/Descargas/CONSIGNACIONES MARZO 2026.docx"),
        Path("/home/gebert/Descargas/CONSIGNACIONES_MARZO_2026_TGlRndz.docx"),
    ]
    doc_path = next(
        (candidate for candidate in candidates if candidate.exists()), candidates[0]
    )

    list_jobs_payload = _print_json("list_jobs", server.list_jobs())
    upload_payload = None
    upload_payload_source = None
    for candidate in candidates:
        if not candidate.exists():
            continue
        upload_payload_source = candidate
        upload_payload = json.loads(server.upload_document(str(candidate)))
        if upload_payload.get("ok") and upload_payload.get("data"):
            doc_path = candidate
            break
    if upload_payload is None:
        raise SystemExit("No usable DOCX candidate was found")
    print(f"upload_source: {upload_payload_source}")
    print("upload_document:")
    print(json.dumps(upload_payload, ensure_ascii=False, indent=2, default=str))

    upload_data = upload_payload.get("data") or {}
    job_id = upload_data.get("id") or upload_data.get("job_id")
    if not job_id:
        raise SystemExit("upload_document did not return id/job_id")

    process_run_exists = ProcessRun.objects.filter(pk=job_id).exists()
    print(f"ProcessRun exists: {process_run_exists}")

    process_payload = _print_json("process_job", server.process_job(int(job_id)))
    status_payload = _print_json("get_job_status", server.get_job_status(int(job_id)))
    logs_payload = _print_json("get_job_logs", server.get_job_logs(int(job_id)))

    print("\nResumen:")
    print(f"list_jobs ejecutado: sí")
    print(f"upload_document ejecutado: sí")
    print(f"job_id creado: {job_id}")
    print(f"process_job ejecutado: sí")
    print(f"estado final: {status_payload.get('data', {}).get('status')}")
    print(
        f"error real: {process_payload.get('detail') or status_payload.get('detail')}"
    )
    print(f"logs_count: {len(logs_payload.get('data') or [])}")
    print(f"list_jobs_count: {len(list_jobs_payload.get('data') or [])}")
    print("\nArchivos modificados: ninguno")
    print("Comandos ejecutados: script directo MCP + consultas ORM locales")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
