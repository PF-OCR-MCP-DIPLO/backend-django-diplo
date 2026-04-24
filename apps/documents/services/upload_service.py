from hashlib import sha256
from pathlib import Path
import zipfile

from django.core.files.base import ContentFile
from django.db import transaction

from apps.documents.services.docx_image_extractor import (
    extract_images_in_order,
    extract_text_from_docx,
)
from apps.processing.models import ProcessRun, SourceImage
from apps.processing.services.settings_service import (
    as_snapshot_dict,
    get_runtime_config,
)


def create_process_run_from_upload(uploaded_file):
    process_run = ProcessRun.objects.create(
        original_filename=uploaded_file.name,
        status=ProcessRun.Status.UPLOADED,
        provider_config_snapshot=_provider_snapshot(),
    )
    try:
        uploaded_file.seek(0)
        process_run.source_docx.save(uploaded_file.name, uploaded_file, save=True)
        process_run.source_docx.open("rb")
        try:
            extracted_images = extract_images_in_order(process_run.source_docx)
            # Extract text from the document
            process_run.source_docx.seek(0)
            extracted_text = extract_text_from_docx(process_run.source_docx)
            process_run.extracted_text = extracted_text
            process_run.save(update_fields=["extracted_text", "updated_at"])
        except (zipfile.BadZipFile, KeyError, ValueError) as error:
            raise UploadValidationError(
                code="invalid_docx",
                message="El archivo .docx no es valido o esta corrupto.",
                details={"reason": str(error)},
            ) from error
        process_run.source_docx.close()
        if not extracted_images:
            raise UploadValidationError(
                code="docx_no_images",
                message="El archivo .docx no contiene imagenes embebidas para procesar.",
            )
        with transaction.atomic():
            for extracted in extracted_images:
                filename = _build_image_filename(
                    process_run.id, extracted.sequence_index, extracted.source_name
                )
                source_image = SourceImage(
                    process_run=process_run,
                    sequence_index=extracted.sequence_index,
                    source_name=extracted.source_name,
                    content_hash=sha256(extracted.binary).hexdigest(),
                    ocr_status=SourceImage.OCRStatus.PENDING,
                )
                source_image.image_file.save(
                    filename, ContentFile(extracted.binary), save=True
                )
            process_run.total_images = len(extracted_images)
            process_run.save(update_fields=["total_images", "updated_at"])
        return process_run
    except Exception:
        process_run.source_docx.delete(save=False)
        process_run.delete()
        raise


class UploadValidationError(Exception):
    def __init__(self, *, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _build_image_filename(process_run_id, sequence_index, source_name):
    suffix = Path(source_name).suffix or ".bin"
    return f"process_runs/{process_run_id}/images/{sequence_index:04d}{suffix}"


def _provider_snapshot():
    return as_snapshot_dict(get_runtime_config())
