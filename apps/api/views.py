from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.auth import ApiKeyPermission
from apps.api.errors import api_error_response
from apps.api.serializers import (
    AssistantChatSerializer,
    BulkDepositCorrectionSerializer,
    ExtractionLogSerializer,
    ProcessingSettingsSerializer,
    ProcessRunDetailSerializer,
    ProcessRunListSerializer,
    UploadDocumentSerializer,
)
from apps.api.services.assistant_chat import AssistantChatService
from apps.documents.services.upload_service import (
    UploadValidationError,
    create_process_run_from_upload,
)
from apps.processing.models import ProcessRun
from apps.processing.services.excel_exporter import export_job_to_excel
from apps.processing.services.diagnostics import (
    summarize_job_diagnostics,
    summarize_processing_state,
    summarize_provider_health,
)
from apps.processing.services.job_cleanup import delete_job_and_files
from apps.processing.services.job_runner import start_job_processing
from apps.processing.services.manual_corrections import (
    apply_deposit_corrections,
    reprocess_failed_sources,
    reprocess_source_image,
)
from apps.processing.services.orchestrator import process_job
from apps.processing.services.settings_service import (
    available_options,
    get_or_create_processing_settings,
    get_ollama_models_snapshot,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


class DocumentUploadView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
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
    permission_classes = [ApiKeyPermission]

    def get(self, request):
        jobs = ProcessRun.objects.order_by("-created_at")
        serializer = ProcessRunListSerializer(jobs, many=True)
        return Response(serializer.data)


class JobDetailView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def get(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        serializer = ProcessRunDetailSerializer(job, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images"), pk=pk
        )
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_delete_conflict",
                message="No puedes borrar una ejecucion mientras sigue procesando.",
                details={"status": job.status},
            )
        delete_job_and_files(job)
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobProcessView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
    throttle_scope = "jobs_process"

    def post(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        force = str(request.query_params.get("force") or "").lower() in {
            "1",
            "true",
            "yes",
        }
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_already_processing",
                message="Esta ejecucion ya se encuentra en procesamiento.",
            )
        if job.status == ProcessRun.Status.COMPLETED and not force:
            serializer = ProcessRunDetailSerializer(job, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        if job.status == ProcessRun.Status.COMPLETED_WITH_ERRORS and not force:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_has_partial_errors",
                message=(
                    "La ejecucion tiene errores parciales. Usa reprocess-failed "
                    "o reprocesa una fuente especifica."
                ),
                details={
                    "status": job.status,
                    "reprocess_failed_url": f"/api/jobs/{job.pk}/reprocess-failed/",
                },
            )
        if settings.PROCESS_JOBS_ASYNC:
            try:
                started = start_job_processing(job, force=force)
            except RuntimeError as error:
                if str(error) == "job_already_processing":
                    return api_error_response(
                        status_code=status.HTTP_409_CONFLICT,
                        code="job_already_processing",
                        message="Esta ejecucion ya se encuentra en procesamiento.",
                    )
                raise
            serializer = ProcessRunDetailSerializer(
                started, context={"request": request}
            )
            return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

        processed = process_job(job)
        processed = ProcessRun.objects.prefetch_related("source_images__deposits").get(
            pk=processed.pk
        )
        serializer = ProcessRunDetailSerializer(processed, context={"request": request})
        return Response(serializer.data)


class JobReprocessFailedView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
    throttle_scope = "jobs_process"

    def post(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_already_processing",
                message="Esta ejecucion ya se encuentra en procesamiento.",
            )
        updated_job = reprocess_failed_sources(job)
        response_serializer = ProcessRunDetailSerializer(
            updated_job, context={"request": request}
        )
        return Response(response_serializer.data)


class JobSourceImageReprocessView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
    throttle_scope = "jobs_process"

    def post(self, request, pk, source_image_id):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_already_processing",
                message="Esta ejecucion ya se encuentra en procesamiento.",
            )
        source_image = job.source_images.filter(pk=source_image_id).first()
        if source_image is None:
            return api_error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="source_image_not_found",
                message="La fuente no pertenece a esta ejecucion.",
            )
        try:
            updated_job = reprocess_source_image(job, source_image)
        except ValueError as error:
            return api_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="source_image_not_reprocessable",
                message=str(error),
            )
        response_serializer = ProcessRunDetailSerializer(
            updated_job, context={"request": request}
        )
        return Response(response_serializer.data)


class JobExportView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
    throttle_scope = "jobs_export"

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
    permission_classes = [ApiKeyPermission]

    def get(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        logs = job.extraction_logs.select_related("source_image").order_by(
            "sequence_index", "id"
        )
        serializer = ExtractionLogSerializer(logs, many=True)
        return Response(serializer.data)


class JobDiagnosticsView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def get(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related(
                "source_images__deposits",
                "source_images__extraction_logs",
                "extraction_logs",
            ),
            pk=pk,
        )
        return Response(summarize_job_diagnostics(job))


class JobProcessingStateView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def get(self, request, pk):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images", "extraction_logs"),
            pk=pk,
        )
        return Response(summarize_processing_state(job))


class ProviderHealthView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def get(self, request):
        return Response(summarize_provider_health())


class JobDepositsBulkUpdateView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def patch(self, request, pk):
        job = get_object_or_404(ProcessRun, pk=pk)
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_not_editable",
                message="No puedes corregir resultados mientras la ejecucion sigue procesando.",
            )
        serializer = BulkDepositCorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated_job = apply_deposit_corrections(
                job, serializer.validated_data["items"]
            )
        except ValueError as error:
            message = (
                str(error.args[0]) if error.args else "Invalid deposit corrections."
            )
            details = error.args[1] if len(error.args) > 1 else None
            return api_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_deposit_corrections",
                message=message,
                details=details,
            )
        response_serializer = ProcessRunDetailSerializer(
            updated_job, context={"request": request}
        )
        return Response(response_serializer.data)


class JobDepositReprocessView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def post(self, request, pk, deposit_id):
        job = get_object_or_404(
            ProcessRun.objects.prefetch_related("source_images__deposits"), pk=pk
        )
        if job.status == ProcessRun.Status.PROCESSING:
            return api_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="job_not_editable",
                message="No puedes reprocesar resultados mientras la ejecucion sigue procesando.",
            )
        deposit = (
            job.deposits.select_related("source_image").filter(pk=deposit_id).first()
        )
        if deposit is None:
            return api_error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="deposit_not_found",
                message="La consignacion no pertenece a esta ejecucion.",
            )
        updated_job = reprocess_source_image(job, deposit.source_image)
        response_serializer = ProcessRunDetailSerializer(
            updated_job, context={"request": request}
        )
        return Response(response_serializer.data)


class ProcessingSettingsView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]
    throttle_scope = "processing_settings"

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
    permission_classes = [ApiKeyPermission]

    def get(self, request):
        return Response(available_options())


class OllamaModelsView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def get(self, request):
        return Response(get_ollama_models_snapshot())


class AssistantChatView(APIView):
    authentication_classes = []
    permission_classes = [ApiKeyPermission]

    def post(self, request):
        serializer = AssistantChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = AssistantChatService()
        response = service.answer(serializer.validated_data)
        settings_obj = get_or_create_processing_settings()
        return Response(
            service.finalize_response(
                response,
                show_debug_details=bool(settings_obj.assistant_show_debug_details),
            )
        )
