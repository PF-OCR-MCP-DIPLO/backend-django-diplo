"""Extracción de imágenes y texto embebido desde documentos DOCX.

El extractor recorre el paquete OpenXML para reconstruir el orden de aparición
de las imágenes y el texto base que sirve como contexto de procesamiento.
"""

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath

from django.conf import settings

NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass
class ExtractedImageFile:
    """Representa una imagen recuperada del DOCX junto a su orden estable."""

    sequence_index: int
    source_name: str
    binary: bytes
    content_hash: str = ""
    relationship_id: str = ""
    package_target: str = ""
    skipped_duplicate_sources: list[dict] | None = None


class DocxUnsupportedContentError(ValueError):
    """El DOCX es válido, pero contiene elementos no soportados por el extractor."""


def extract_images_in_order(docx_file):
    """Recupera las imágenes embebidas del DOCX respetando su secuencia visual.

    Raises:
        ValueError: Si el documento contiene referencias no soportadas.
    """
    docx_file.seek(0)
    if not zipfile.is_zipfile(docx_file):
        raise zipfile.BadZipFile("Uploaded file is not a valid ZIP/DOCX archive.")
    docx_file.seek(0)
    with zipfile.ZipFile(docx_file) as archive:
        document_xml = archive.read("word/document.xml")
        rels_xml = archive.read("word/_rels/document.xml.rels")
        document_root = ET.fromstring(document_xml)
        rels_root = ET.fromstring(rels_xml)
        rel_map = {}
        for relationship in rels_root.findall("pr:Relationship", NAMESPACES):
            rel_id = relationship.attrib.get("Id")
            target = relationship.attrib.get("Target")
            if rel_id and target:
                rel_map[rel_id] = _normalize_target(target)
        images = []
        seen_targets = {}
        seen_recent_content = {}
        raw_reference_index = 0
        max_image_bytes = int(
            getattr(
                settings,
                "EXTRACTED_IMAGE_MAX_BYTES",
                5 * 1024 * 1024,
            )
        )
        for element in document_root.iter():
            rel_id = _extract_relationship_id(element)
            if not rel_id:
                continue
            target = rel_map.get(rel_id)
            if not target or target not in archive.namelist():
                continue
            raw_reference_index += 1
            binary = archive.read(target)
            if len(binary) > max_image_bytes:
                raise DocxUnsupportedContentError(
                    "Extracted image exceeds maximum allowed size."
                )
            content_hash = sha256(binary).hexdigest()
            source_name = PurePosixPath(target).name
            duplicate_of = seen_targets.get(target)
            duplicate_reason = "same_package_target" if duplicate_of else ""
            previous_content = seen_recent_content.get(content_hash)
            if not duplicate_of and previous_content:
                previous_reference_index, previous_image = previous_content
                if raw_reference_index - previous_reference_index <= 1:
                    duplicate_of = previous_image
                    duplicate_reason = "adjacent_same_binary_content"

            if duplicate_of:
                duplicate_of.skipped_duplicate_sources = (
                    duplicate_of.skipped_duplicate_sources or []
                )
                duplicate_of.skipped_duplicate_sources.append(
                    {
                        "source_name": source_name,
                        "relationship_id": rel_id,
                        "package_target": target,
                        "content_hash": content_hash,
                        "raw_reference_index": raw_reference_index,
                        "reason": duplicate_reason,
                    }
                )
                seen_targets[target] = duplicate_of
                seen_recent_content[content_hash] = (
                    raw_reference_index,
                    duplicate_of,
                )
                continue

            sequence_index = len(images) + 1
            extracted = ExtractedImageFile(
                sequence_index=sequence_index,
                source_name=source_name,
                binary=binary,
                content_hash=content_hash,
                relationship_id=rel_id,
                package_target=target,
                skipped_duplicate_sources=[],
            )
            images.append(extracted)
            seen_targets[target] = extracted
            seen_recent_content[content_hash] = (
                raw_reference_index,
                extracted,
            )
        return images


def extract_text_from_docx(docx_file):
    """Extrae texto plano embebido del DOCX como contexto auxiliar."""
    docx_file.seek(0)
    text_content = []

    try:
        with zipfile.ZipFile(docx_file) as archive:
            # Read the main document
            if "word/document.xml" in archive.namelist():
                document_xml = archive.read("word/document.xml")
                document_root = ET.fromstring(document_xml)

                # Extract text from paragraphs
                for paragraph in document_root.iter():
                    if paragraph.tag.endswith("}p"):  # Paragraph
                        para_text = []
                        for run in paragraph.iter():
                            if run.tag.endswith("}t"):  # Text run
                                if run.text:
                                    para_text.append(run.text)
                        if para_text:
                            text_content.append("".join(para_text))

        return "\n".join(text_content).strip()
    except Exception:
        return ""


def _normalize_target(target):
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("word", target))


def _extract_relationship_id(element):
    embed = element.attrib.get(f"{{{NAMESPACES['r']}}}embed")
    if embed:
        return embed
    return element.attrib.get(f"{{{NAMESPACES['r']}}}id")
