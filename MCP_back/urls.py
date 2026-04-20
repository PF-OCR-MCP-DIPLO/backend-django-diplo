from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path


def root_view(request):
    return JsonResponse(
        {
            "message": "Backend Django running",
            "health": "/api/health/",
            "admin": "/admin/",
        }
    )


def favicon_view(request):
    return HttpResponse(status=204)


urlpatterns = [
    path("", root_view),
    path("favicon.ico", favicon_view),
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
