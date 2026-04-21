from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.errors import api_error_response
from apps.api.auth import ApiKeyPermission
from apps.api.serializers import (
    ExtractionLogSerializer,
    ProcessRunDetailSerializer,
    ProcessRunListSerializer,
    ProcessingSettingsSerializer,
    UploadDocumentSerializer,
)
from apps.documents.services.upload_service import create_process_run_from_upload
from apps.documents.services.upload_service import UploadValidationError
from apps.processing.models import ProcessRun
from apps.processing.services.excel_exporter import export_job_to_excel
from apps.processing.services.orchestrator import process_job
from apps.processing.services.settings_service import (
    available_options,
    get_or_create_processing_settings,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class DocumentUploadView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "documents_upload"

    def post(self, request):
        serializer = UploadDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            process_run = create_process_run_from_upload(
                serializer.validated_data["file"]
            )
        except UploadValidationError as error:
            return api_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=error.code,
                message=error.message,
                details=error.details or None,
            )
        return Response(
            ProcessRunDetailSerializer(process_run, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class JobListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        jobs = ProcessRun.objects.order_by("-created_at")
        serializer = ProcessRunListSerializer(jobs, many=True)
        return Response(serializer.data)


class JobDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        serializer = ProcessRunDetailSerializer(job, context={"request": request})
        return Response(serializer.data)


class JobProcessView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "jobs_process"

    def get_permissions(self):
        return [ApiKeyPermission()]

    def post(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_already_processing",
                message="Esta ejecucion ya se encuentra en procesamiento.",
            )
        processed = process_job(job)
        processed = ProcessRun.objects.prefetch_related("source_images__deposits").get(
            pk=processed.pk
        )
        serializer = ProcessRunDetailSerializer(processed, context={"request": request})
        return Response(serializer.data)


class JobExportView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "jobs_export"

    def get_permissions(self):
        return [ApiKeyPermission()]

    def post(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        if job.status not in (
            ProcessRun.Status.COMPLETED,
            ProcessRun.Status.COMPLETED_WITH_ERRORS,
        ):
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_not_exportable",
                message="Solo las ejecuciones completadas pueden exportarse.",
                details={"status": job.status},
            )
        exported = export_job_to_excel(job)
        serializer = ProcessRunDetailSerializer(exported, context={"request": request})
        return Response(serializer.data)


class JobLogsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        logs = job.extraction_logs.select_related("source_image").order_by(
            "sequence_index", "id"
        )
        serializer = ExtractionLogSerializer(logs, many=True)
        return Response(serializer.data)


class ProcessingSettingsView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_scope = "processing_settings"

    def get_permissions(self):
        # Read is public for DX; updates require API key when configured.
        if self.request.method.upper() == "PATCH":
            return [ApiKeyPermission()]
        return []

    def get(self, request):
        serializer = ProcessingSettingsSerializer(get_or_create_processing_settings())
        return Response(serializer.data)

    def patch(self, request):
        instance = get_or_create_processing_settings()
        serializer = ProcessingSettingsSerializer(
            instance, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ProcessingSettingsOptionsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response(available_options())
