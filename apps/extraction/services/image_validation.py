MIN_IMAGE_BYTES = 32


def validate_source_image(source_image):
    source_image.image_file.open("rb")
    try:
        binary = source_image.image_file.read()
    finally:
        source_image.image_file.close()
    if len(binary) < MIN_IMAGE_BYTES:
        raise ValueError("Extracted image is too small or corrupt.")
    if not _looks_like_supported_image(binary):
        raise ValueError("Extracted image is invalid or unreadable.")


def _looks_like_supported_image(binary):
    if binary.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if binary.startswith(b"\xff\xd8\xff"):
        return True
    if binary.startswith((b"GIF87a", b"GIF89a")):
        return True
    if binary.startswith(b"BM"):
        return True
    if binary.startswith(b"RIFF") and binary[8:12] == b"WEBP":
        return True
    return False
