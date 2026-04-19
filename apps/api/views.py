from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.serializers import (
    ProcessRunDetailSerializer,
    ProcessRunListSerializer,
    UploadDocumentSerializer,
)
from apps.documents.services.upload_service import create_process_run_from_upload
from apps.processing.models import ProcessRun
from apps.processing.services.excel_exporter import export_job_to_excel
from apps.processing.services.orchestrator import process_job


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class DocumentUploadView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = UploadDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        process_run = create_process_run_from_upload(serializer.validated_data["file"])
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

    def post(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        if job.status == ProcessRun.Status.PROCESSING:
            return Response(
                {"detail": "This job is already processing."},
                status=status.HTTP_409_CONFLICT,
            )
        processed = process_job(job)
        serializer = ProcessRunDetailSerializer(processed, context={"request": request})
        return Response(serializer.data)


class JobExportView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        if job.status != ProcessRun.Status.COMPLETED:
            return Response(
                {"detail": "Only completed jobs can be exported."},
                status=status.HTTP_409_CONFLICT,
            )
        exported = export_job_to_excel(job)
        serializer = ProcessRunDetailSerializer(exported, context={"request": request})
        return Response(serializer.data)
