import shutil
import subprocess

from apps.extraction.providers.ocr.base import BaseOCRProvider


class TesseractOCRProvider(BaseOCRProvider):
    def extract_text(self, image_file, model_name="spa"):
        binary = shutil.which("tesseract")
        if not binary:
            raise RuntimeError("Tesseract binary is not available")
        image_path = getattr(image_file, "path", "")
        if not image_path:
            raise RuntimeError("Image path is not available for tesseract")
        command = [binary, image_path, "stdout", "-l", model_name or "spa"]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            error_text = completed.stderr.strip() or "unknown tesseract error"
            raise RuntimeError(error_text)
        return completed.stdout
