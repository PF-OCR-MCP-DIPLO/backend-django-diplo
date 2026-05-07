"""Rutas públicas de la API REST del backend.

Agrupa endpoints de carga, procesamiento, exportación, diagnóstico y chat del
asistente bajo el prefijo `/api/`.
"""

from django.urls import path

from apps.api.views import (
    AssistantChatView,
    DocumentUploadView,
    HealthView,
    JobDepositsBulkUpdateView,
    JobDetailView,
    JobDiagnosticsView,
    JobExportView,
    JobListView,
    JobLogsView,
    JobProcessView,
    JobProcessingStateView,
    JobTraceView,
    JobDepositReprocessView,
    JobReprocessFailedView,
    JobSourceImageReprocessView,
    OllamaModelsView,
    ProviderHealthView,
    ProcessingSettingsOptionsView,
    ProcessingSettingsView,
)

urlpatterns = [
    path("", HealthView.as_view(), name="api-root"),
    path("health/", HealthView.as_view(), name="health"),
    path("assistant/chat/", AssistantChatView.as_view(), name="assistant-chat"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/<int:pk>/", JobDetailView.as_view(), name="job-detail"),
    path(
        "jobs/<int:pk>/deposits/",
        JobDepositsBulkUpdateView.as_view(),
        name="job-deposits-bulk-update",
    ),
    path(
        "jobs/<int:pk>/deposits/<int:deposit_id>/reprocess/",
        JobDepositReprocessView.as_view(),
        name="job-deposit-reprocess",
    ),
    path("jobs/<int:pk>/logs/", JobLogsView.as_view(), name="job-logs"),
    path("jobs/<int:pk>/trace/", JobTraceView.as_view(), name="job-trace"),
    path(
        "jobs/<int:pk>/diagnostics/",
        JobDiagnosticsView.as_view(),
        name="job-diagnostics",
    ),
    path(
        "jobs/<int:pk>/processing-state/",
        JobProcessingStateView.as_view(),
        name="job-processing-state",
    ),
    path("jobs/<int:pk>/process/", JobProcessView.as_view(), name="job-process"),
    path(
        "jobs/<int:pk>/reprocess-failed/",
        JobReprocessFailedView.as_view(),
        name="job-reprocess-failed",
    ),
    path(
        "jobs/<int:pk>/source-images/<int:source_image_id>/reprocess/",
        JobSourceImageReprocessView.as_view(),
        name="job-source-image-reprocess",
    ),
    path("jobs/<int:pk>/export/", JobExportView.as_view(), name="job-export"),
    path(
        "processing/settings/",
        ProcessingSettingsView.as_view(),
        name="processing-settings",
    ),
    path(
        "processing/settings/options/",
        ProcessingSettingsOptionsView.as_view(),
        name="processing-settings-options",
    ),
    path(
        "processing/ollama/models/",
        OllamaModelsView.as_view(),
        name="processing-ollama-models",
    ),
    path(
        "processing/provider-health/",
        ProviderHealthView.as_view(),
        name="processing-provider-health",
    ),
]
