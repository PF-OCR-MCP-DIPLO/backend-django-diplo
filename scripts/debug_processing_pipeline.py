#!/usr/bin/env python
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Debug OCR/LLM processing pipeline.")
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--stub", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--async", dest="async_mode", action="store_true")
    parser.add_argument("--single-image", type=int)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--ocr-only", action="store_true")
    parser.add_argument("--llm-only-from-existing-ocr", action="store_true")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--max-images", type=int)
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--report-md", type=Path)
    return parser.parse_args()


args = parse_args()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MCP_back.settings")
if args.stub and args.real:
    raise SystemExit("--stub and --real are mutually exclusive")
if args.stub:
    os.environ["STUB_PROVIDERS"] = "1"
elif args.real:
    os.environ["STUB_PROVIDERS"] = "0"
else:
    os.environ.setdefault("STUB_PROVIDERS", "1")
if args.sync:
    os.environ["PROCESS_JOBS_ASYNC"] = "0"
if args.async_mode:
    os.environ["PROCESS_JOBS_ASYNC"] = "1"
if args.timeout:
    os.environ["OLLAMA_TIMEOUT"] = str(args.timeout)

import django

django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.services.upload_service import create_process_run_from_upload
from apps.processing.models import ProcessRun, SourceImage
from apps.processing.services.agents import (
    OCRAgent,
    ProcessingSupervisorAgent,
    StructuringAgent,
    ValidationPersistenceAgent,
)
from apps.processing.services.diagnostics import (
    record_processing_event,
    stage_timer,
    summarize_job_diagnostics,
)
from apps.processing.services.job_runner import start_job_processing
from apps.processing.services.orchestrator import (
    prepare_job_for_full_processing,
    real_source_images_queryset,
)
from apps.processing.services.settings_service import (
    get_or_create_processing_settings,
    get_runtime_config,
)


def build_deposit_png(reference: str, value: str, date: str, hour: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 360), "white")
    draw = ImageDraw.Draw(image)
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_body = ImageFont.truetype("DejaVuSans.ttf", 32)
    except OSError:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
    draw.text((40, 35), "COMPROBANTE DE CONSIGNACION", fill="black", font=font_title)
    draw.text((40, 110), f"Referencia: {reference}", fill="black", font=font_body)
    draw.text((40, 165), f"Valor: {value}", fill="black", font=font_body)
    draw.text((40, 220), f"Fecha: {date}", fill="black", font=font_body)
    draw.text((40, 275), f"Hora: {hour}", fill="black", font=font_body)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_docx_with_images_and_text() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rIdImage2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Texto DOCX guardado como contexto, no como SourceImage.</w:t></w:r></w:p>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage2"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "word/media/image1.png",
            build_deposit_png("REF001", "50000", "15/04/2026", "09:30"),
        )
        archive.writestr(
            "word/media/image2.png",
            build_deposit_png("REF002", "75000", "16/04/2026", "10:45"),
        )
    buffer.seek(0)
    return buffer.getvalue()


def load_or_create_job() -> ProcessRun:
    if args.job_id:
        return ProcessRun.objects.get(pk=args.job_id)
    if args.file:
        payload = args.file.read_bytes()
        filename = args.file.name
    else:
        payload = build_docx_with_images_and_text()
        filename = "debug_pipeline.docx"
    upload = SimpleUploadedFile(
        filename,
        payload,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    return create_process_run_from_upload(upload)


def selected_images(job: ProcessRun) -> list[SourceImage]:
    queryset = real_source_images_queryset(job).order_by("sequence_index", "id")
    if args.single_image:
        queryset = queryset.filter(pk=args.single_image)
    images = list(queryset)
    if args.max_images:
        images = images[: args.max_images]
    return images


def set_timeout_setting() -> int | None:
    if not args.timeout:
        return None
    settings_obj = get_or_create_processing_settings()
    previous = settings_obj.request_timeout_seconds
    settings_obj.request_timeout_seconds = args.timeout
    settings_obj.save(update_fields=["request_timeout_seconds", "updated_at"])
    return previous


def run_subset_sync(job: ProcessRun) -> ProcessRun:
    if args.llm_only_from_existing_ocr:
        prepared_job = ProcessRun.objects.get(pk=job.pk)
        runtime_config = get_runtime_config()
        prepared_job.status = ProcessRun.Status.PROCESSING
        prepared_job.started_at = timezone.now()
        prepared_job.finished_at = None
        prepared_job.error_message = ""
        prepared_job.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "error_message",
                "updated_at",
            ]
        )
    else:
        prepared_job, runtime_config = prepare_job_for_full_processing(job)
    images = selected_images(prepared_job)
    supervisor = ProcessingSupervisorAgent()
    ocr_agent = OCRAgent()
    structuring_agent = StructuringAgent()
    validation_agent = ValidationPersistenceAgent()
    failed_images = 0

    for source_image in images:
        try:
            if args.llm_only_from_existing_ocr:
                raw_text = source_image.ocr_raw_text
                if not raw_text:
                    raise RuntimeError("SourceImage has no existing ocr_raw_text")
                source_image.deposits.all().delete()
                structured = structuring_agent.run(
                    prepared_job, source_image, raw_text, runtime_config
                )
                with stage_timer(
                    process_run=prepared_job,
                    source_image=source_image,
                    stage="validation_persistence",
                    runtime_config=runtime_config,
                ) as event:
                    records_count = validation_agent.run(
                        prepared_job,
                        source_image,
                        structured["records"],
                        runtime_config,
                    )
                    event["records_count"] = records_count
                source_image.ocr_status = SourceImage.OCRStatus.PROCESSED
                source_image.error_message = ""
                source_image.save(
                    update_fields=["ocr_status", "error_message", "updated_at"]
                )
                continue

            if args.ocr_only or args.skip_llm:
                ocr_result = ocr_agent.run(prepared_job, source_image, runtime_config)
                source_image.ocr_raw_text = ocr_result["text"]
                source_image.ocr_provider = ocr_result["provider"]
                source_image.ocr_status = SourceImage.OCRStatus.PROCESSED
                source_image.error_message = ""
                source_image.save(
                    update_fields=[
                        "ocr_raw_text",
                        "ocr_provider",
                        "ocr_status",
                        "error_message",
                        "updated_at",
                    ]
                )
                record_processing_event(
                    process_run=prepared_job,
                    source_image=source_image,
                    stage="llm_structuring",
                    status="skipped",
                    runtime_config=runtime_config,
                    raw_payload={"reason": "ocr_only" if args.ocr_only else "skip_llm"},
                )
                continue

            supervisor.process_image(
                prepared_job,
                source_image,
                runtime_config,
                lambda process_run, image, stage, config, **kwargs: record_processing_event(
                    process_run=process_run,
                    source_image=image,
                    stage=stage,
                    status="failed" if kwargs.get("is_error", False) else "completed",
                    runtime_config=config,
                    provider=kwargs.get("provider", ""),
                    model=kwargs.get("model", ""),
                    raw_payload=kwargs.get("raw_payload", {}),
                    raw_text=kwargs.get("raw_text", ""),
                    notes=kwargs.get("notes", ""),
                ),
            )
        except Exception as error:
            failed_images += 1
            source_image.ocr_status = SourceImage.OCRStatus.FAILED
            source_image.error_message = str(error)
            source_image.save(
                update_fields=["ocr_status", "error_message", "updated_at"]
            )
            record_processing_event(
                process_run=prepared_job,
                source_image=source_image,
                stage="image_failed",
                status="failed",
                runtime_config=runtime_config,
                error=error,
            )

    prepared_job.refresh_from_db()
    total_images = real_source_images_queryset(prepared_job).count()
    failed_total = (
        real_source_images_queryset(prepared_job)
        .filter(ocr_status=SourceImage.OCRStatus.FAILED)
        .count()
    )
    prepared_job.total_images = total_images
    prepared_job.total_records = prepared_job.deposits.count()
    prepared_job.finished_at = timezone.now()
    if args.ocr_only or args.skip_llm:
        prepared_job.status = (
            ProcessRun.Status.COMPLETED_WITH_ERRORS
            if failed_total
            else ProcessRun.Status.COMPLETED
        )
    elif failed_total == total_images and prepared_job.total_records == 0:
        prepared_job.status = ProcessRun.Status.FAILED
    elif failed_total:
        prepared_job.status = ProcessRun.Status.COMPLETED_WITH_ERRORS
    else:
        prepared_job.status = ProcessRun.Status.COMPLETED
    prepared_job.error_message = ""
    prepared_job.save(
        update_fields=[
            "status",
            "total_images",
            "total_records",
            "finished_at",
            "error_message",
            "updated_at",
        ]
    )
    record_processing_event(
        process_run=prepared_job,
        stage="job_finished",
        status="completed",
        runtime_config=runtime_config,
        raw_payload={
            "status": prepared_job.status,
            "selected_images": [image.pk for image in images],
            "failed_images": failed_images,
        },
    )
    return prepared_job


def run_async(job: ProcessRun) -> ProcessRun:
    started = start_job_processing(job, force=True)
    deadline = time.monotonic() + (args.timeout or 90)
    client = APIClient()
    while time.monotonic() < deadline:
        current = ProcessRun.objects.get(pk=started.pk)
        if current.status in {
            ProcessRun.Status.COMPLETED,
            ProcessRun.Status.COMPLETED_WITH_ERRORS,
            ProcessRun.Status.FAILED,
        }:
            return current
        response = client.get(f"/api/jobs/{started.pk}/processing-state/")
        if response.status_code == 200:
            payload = response.json()
            print(
                f"poll status={payload['status']} stage={payload['current_stage']} "
                f"images={payload['processed_images']}/{payload['total_images']}"
            )
        time.sleep(1.5)
    return ProcessRun.objects.get(pk=started.pk)


def probable_cause(report: dict) -> str:
    summary = report["summary"]
    if summary["stale_processing"]:
        return "job stale in processing"
    if (
        summary["total_llm_duration_ms"] > summary["total_ocr_duration_ms"] * 2
        and summary["llm_calls"]
    ):
        return "LLM structuring is the dominant cost"
    if (
        summary["total_ocr_duration_ms"] > summary["total_llm_duration_ms"] * 2
        and summary["ocr_calls"]
    ):
        return "OCR is the dominant cost"
    if summary["failed_images"]:
        return "one or more images/providers failed"
    return "no dominant bottleneck detected in this run"


def print_report(report: dict) -> None:
    summary = report["summary"]
    job = report["job"]
    print("\nDOCX:")
    print(f"- images_extracted: {job['total_images']}")
    print(
        "- total_image_bytes: "
        f"{round(sum((item.get('image_bytes') or 0) for item in report['source_images']) / (1024 * 1024), 2)} MB"
    )
    print("\nPROCESS:")
    print(f"- OCR calls: {summary['ocr_calls']}")
    print(f"- LLM calls: {summary['llm_calls']}")
    print(f"- OCR total: {round(summary['total_ocr_duration_ms'] / 1000, 2)}s")
    print(f"- LLM total: {round(summary['total_llm_duration_ms'] / 1000, 2)}s")
    print(f"- slowest image: {summary['slowest_source_image_id']}")
    print(f"- slowest stage: {summary['slowest_stage']}")
    print(f"- final status: {job['status']}")
    print(f"- records: {job['total_records']}")
    print("\nSTAGES:")
    print(
        "stage | status | duration_ms | provider/model | source_image_id | records | error"
    )
    for event in report["events"]:
        if event.get("status") == "started":
            continue
        provider_model = "/".join(
            item for item in [event.get("provider"), event.get("model")] if item
        )
        print(
            f"{event['stage']} | {event.get('status')} | {event.get('duration_ms') or 0} | "
            f"{provider_model or '-'} | {event.get('source_image_id') or '-'} | "
            f"{event.get('records_count') or 0} | {event.get('error_message') or ''}"
        )
    print("\nDIAGNOSIS:")
    print(f"- probable cause: {probable_cause(report)}")
    for recommendation in report["recommendations"]:
        print(f"- recommendation: {recommendation}")


def write_markdown(report: dict, path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# Processing Diagnostic Report",
        "",
        f"- job_id: {report['job']['id']}",
        f"- status: {report['job']['status']}",
        f"- probable_cause: {probable_cause(report)}",
        f"- ocr_calls: {summary['ocr_calls']}",
        f"- llm_calls: {summary['llm_calls']}",
        f"- total_ocr_duration_ms: {summary['total_ocr_duration_ms']}",
        f"- total_llm_duration_ms: {summary['total_llm_duration_ms']}",
        f"- slowest_stage: {summary['slowest_stage']}",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in report["recommendations"])
    lines.extend(
        [
            "",
            "## Events",
            "",
            "| stage | status | ms | image | provider | model | error |",
            "|---|---:|---:|---:|---|---|---|",
        ]
    )
    for event in report["events"]:
        if event.get("status") == "started":
            continue
        lines.append(
            f"| {event['stage']} | {event.get('status')} | {event.get('duration_ms') or 0} | "
            f"{event.get('source_image_id') or ''} | {event.get('provider') or ''} | "
            f"{event.get('model') or ''} | {event.get('error_message') or ''} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    previous_timeout = set_timeout_setting()
    try:
        job = load_or_create_job()
        if args.async_mode and not (
            args.ocr_only
            or args.skip_llm
            or args.llm_only_from_existing_ocr
            or args.single_image
            or args.max_images
        ):
            job = run_async(job)
        else:
            job = run_subset_sync(job)
        report = summarize_job_diagnostics(ProcessRun.objects.get(pk=job.pk))
        print_report(report)
        if args.report_json:
            args.report_json.write_text(
                json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
            )
        if args.report_md:
            write_markdown(report, args.report_md)
        if report["job"]["status"] == "failed":
            return 2
        return 0
    finally:
        if previous_timeout is not None:
            settings_obj = get_or_create_processing_settings()
            settings_obj.request_timeout_seconds = previous_timeout
            settings_obj.save(update_fields=["request_timeout_seconds", "updated_at"])


if __name__ == "__main__":
    sys.exit(main())
