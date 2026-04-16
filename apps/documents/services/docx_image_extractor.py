import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass
class ExtractedImageFile:
    sequence_index: int
    source_name: str
    binary: bytes


def extract_images_in_order(docx_file):
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
        sequence_index = 0
        for element in document_root.iter():
            rel_id = _extract_relationship_id(element)
            if not rel_id:
                continue
            target = rel_map.get(rel_id)
            if not target or target not in archive.namelist():
                continue
            sequence_index += 1
            images.append(
                ExtractedImageFile(
                    sequence_index=sequence_index,
                    source_name=PurePosixPath(target).name,
                    binary=archive.read(target),
                )
            )
        return images


def _normalize_target(target):
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("word", target))


def _extract_relationship_id(element):
    embed = element.attrib.get(f"{{{NAMESPACES['r']}}}embed")
    if embed:
        return embed
    return element.attrib.get(f"{{{NAMESPACES['r']}}}id")
