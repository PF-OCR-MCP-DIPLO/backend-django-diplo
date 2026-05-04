import base64
import io
import zipfile

from django.test import SimpleTestCase

from apps.documents.services.docx_image_extractor import extract_images_in_order

PNG_ONE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WnR2xQAAAAASUVORK5CYII="
)
PNG_TWO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mNk+M/wHwAEAQH/5N9sLQAAAABJRU5ErkJggg=="
)


def build_docx():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage2"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/second.png"/>
  <Relationship Id="rIdImage2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/first.png"/>
</Relationships>""",
        )
        archive.writestr("word/media/first.png", PNG_ONE)
        archive.writestr("word/media/second.png", PNG_TWO)
    buffer.seek(0)
    return buffer


def build_docx_with_adjacent_duplicate_content():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <w:body>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage2"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
    <w:p><w:r><w:drawing><a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill><a:blip r:embed="rIdImage3"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:drawing></w:r></w:p>
  </w:body>
</w:document>""",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rIdImage2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
  <Relationship Id="rIdImage3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image3.png"/>
</Relationships>""",
        )
        archive.writestr("word/media/image1.png", PNG_ONE)
        archive.writestr("word/media/image2.png", PNG_ONE)
        archive.writestr("word/media/image3.png", PNG_TWO)
    buffer.seek(0)
    return buffer


class DocxExtractorTests(SimpleTestCase):
    """Protege el contrato de orden de imágenes embebidas dentro del DOCX."""

    def test_extract_images_in_document_order(self):
        images = extract_images_in_order(build_docx())
        self.assertEqual([item.sequence_index for item in images], [1, 2])
        self.assertEqual(
            [item.source_name for item in images], ["first.png", "second.png"]
        )

    def test_skips_adjacent_duplicate_binary_references(self):
        images = extract_images_in_order(build_docx_with_adjacent_duplicate_content())

        self.assertEqual([item.sequence_index for item in images], [1, 2])
        self.assertEqual(
            [item.source_name for item in images], ["image1.png", "image3.png"]
        )
        self.assertEqual(
            images[0].skipped_duplicate_sources[0]["source_name"], "image2.png"
        )
        self.assertEqual(
            images[0].skipped_duplicate_sources[0]["reason"],
            "adjacent_same_binary_content",
        )
