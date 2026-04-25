import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from apps.extraction.providers.ocr.base import BaseOCRProvider


def resolve_tesseract_language(model_name):
    """Map stored `ocr_model` to a Tesseract `-l` value."""
    name = (model_name or "").strip()
    if not name or ":" in name:
        return "spa"
    return name


def preprocess_image_for_ocr(image_file, *, binarize=False, sharpen=False):
    image_file.seek(0)
    with Image.open(image_file) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")
        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        if min(image.size) < 1000:
            image = image.resize((image.width * 2, image.height * 2))
        if sharpen:
            image = image.filter(ImageFilter.SHARPEN)
        if binarize:
            image = image.point(lambda pixel: 255 if pixel > 170 else 0)
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            image.save(temp_file.name, format="PNG")
        finally:
            temp_file.close()
    return Path(temp_file.name)


class TesseractOCRProvider(BaseOCRProvider):
    def extract_text(self, image_file, model_name="spa"):
        binary = shutil.which("tesseract")
        if not binary:
            raise RuntimeError("Tesseract binary is not available")
        image_path = getattr(image_file, "path", "")
        if not image_path:
            raise RuntimeError("Image path is not available for tesseract")
        lang = resolve_tesseract_language(model_name)
        command = [binary, image_path, "stdout", "-l", lang, "--oem", "1", "--psm", "6"]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0 or not completed.stdout.strip():
            fallback_command = [
                binary,
                image_path,
                "stdout",
                "-l",
                lang,
                "--oem",
                "1",
                "--psm",
                "4",
            ]
            fallback_completed = subprocess.run(
                fallback_command, check=False, capture_output=True, text=True
            )
            if fallback_completed.returncode == 0 and fallback_completed.stdout.strip():
                completed = fallback_completed
                command = fallback_command
        if completed.returncode != 0:
            error_text = completed.stderr.strip() or "unknown tesseract error"
            raise RuntimeError(error_text)
        return completed.stdout
