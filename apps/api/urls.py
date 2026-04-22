from django.urls import path

from apps.api.views import (
    DocumentUploadView,
    HealthView,
    JobDetailView,
    JobExportView,
    JobListView,
    JobLogsView,
    JobProcessView,
    ProcessingSettingsOptionsView,
    ProcessingSettingsView,
)

urlpatterns = [
    path("", HealthView.as_view(), name="api-root"),
    path("health/", HealthView.as_view(), name="health"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/<int:pk>/", JobDetailView.as_view(), name="job-detail"),
    path("jobs/<int:pk>/logs/", JobLogsView.as_view(), name="job-logs"),
    path("jobs/<int:pk>/process/", JobProcessView.as_view(), name="job-process"),
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
]
