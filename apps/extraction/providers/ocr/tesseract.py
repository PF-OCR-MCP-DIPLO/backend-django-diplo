import shutil
import subprocess

from apps.extraction.providers.ocr.base import BaseOCRProvider


def resolve_tesseract_language(model_name):
    """Map stored `ocr_model` to a Tesseract `-l` value.

    Vision models (Ollama-style tags like `gemma4:e2b`) share the same DB field
    but are not valid tessdata language names.
    """
    name = (model_name or "").strip()
    if not name or ":" in name:
        return "spa"
    return name


class TesseractOCRProvider(BaseOCRProvider):
    def extract_text(self, image_file, model_name="spa"):
        binary = shutil.which("tesseract")
        if not binary:
            raise RuntimeError("Tesseract binary is not available")
        image_path = getattr(image_file, "path", "")
        if not image_path:
            raise RuntimeError("Image path is not available for tesseract")
        lang = resolve_tesseract_language(model_name)
        command = [binary, image_path, "stdout", "-l", lang]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            error_text = completed.stderr.strip() or "unknown tesseract error"
            raise RuntimeError(error_text)
        return completed.stdout
