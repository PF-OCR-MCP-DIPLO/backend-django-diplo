from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import exceptions, status

from apps.api.auth import ApiKeyPermission, api_key_required
from apps.api.exception_handlers import api_exception_handler
from apps.api.serializers import UploadDocumentSerializer


class ApiKeyPermissionTests(SimpleTestCase):
    """Protege el contrato de acceso por API key en entorno abierto y cerrado."""

    @override_settings(API_KEY="secret", ALLOW_OPEN_API_FOR_DEV=False)
    def test_permission_accepts_matching_header(self):
        request = type("Request", (), {"META": {"HTTP_X_API_KEY": "secret"}})()
        self.assertTrue(ApiKeyPermission().has_permission(request, object()))
        self.assertTrue(api_key_required())

    @override_settings(API_KEY="secret", ALLOW_OPEN_API_FOR_DEV=False)
    def test_permission_rejects_wrong_header(self):
        request = type("Request", (), {"META": {"HTTP_X_API_KEY": "wrong"}})()
        self.assertFalse(ApiKeyPermission().has_permission(request, object()))

    @override_settings(API_KEY="", ALLOW_OPEN_API_FOR_DEV=True)
    def test_permission_allows_open_dev_mode(self):
        request = type("Request", (), {"META": {}})()
        self.assertTrue(ApiKeyPermission().has_permission(request, object()))
        self.assertFalse(api_key_required())

    @override_settings(API_KEY="", ALLOW_OPEN_API_FOR_DEV=False)
    def test_permission_rejects_when_prod_has_no_api_key(self):
        request = type("Request", (), {"META": {}})()
        self.assertFalse(ApiKeyPermission().has_permission(request, object()))
        self.assertTrue(api_key_required())


class ApiExceptionHandlerTests(SimpleTestCase):
    """Verifica el sobre de errores uniforme que consume el frontend."""

    def test_validation_error_uses_standard_envelope(self):
        response = api_exception_handler(
            exceptions.ValidationError({"file": ["Solo .docx"]}),
            {"view": object(), "request": object()},
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertIn("file", response.data["error"]["details"])

    def test_not_found_uses_standard_envelope(self):
        response = api_exception_handler(
            exceptions.NotFound("No existe"),
            {"view": object(), "request": object()},
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "not_found")
        self.assertEqual(response.data["error"]["message"], "No existe")

    def test_permission_denied_uses_forbidden_code(self):
        response = api_exception_handler(
            DjangoPermissionDenied("No autorizado"),
            {"view": object(), "request": object()},
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "forbidden")


class UploadDocumentSerializerTests(SimpleTestCase):
    """Valida el contrato de entrada del upload antes de llegar a la vista."""

    @override_settings(DOCX_MAX_UPLOAD_BYTES=8)
    def test_rejects_file_larger_than_limit(self):
        serializer = UploadDocumentSerializer(
            data={
                "file": SimpleUploadedFile(
                    "large.docx",
                    b"123456789",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_rejects_invalid_extension(self):
        serializer = UploadDocumentSerializer(
            data={
                "file": SimpleUploadedFile("bad.txt", b"123", content_type="text/plain")
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_accepts_valid_docx(self):
        serializer = UploadDocumentSerializer(
            data={
                "file": SimpleUploadedFile(
                    "good.docx",
                    b"1234",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            }
        )

        self.assertTrue(serializer.is_valid())
