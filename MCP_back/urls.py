"""Rutas raíz del backend Django.

Expone health checks, documentación OpenAPI, administración y el prefijo
principal de la API REST.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def root_view(request):
    """Devuelve un payload mínimo para comprobar que el backend responde.

    Returns:
        JsonResponse con enlaces básicos de la aplicación.
    """
    return JsonResponse(
        {
            "message": "Backend Django running",
            "health": "/api/health/",
            "admin": "/admin/",
        }
    )


def favicon_view(request):
    """Responde a `favicon.ico` sin cargar contenido adicional."""
    return HttpResponse(status=204)


urlpatterns = [
    path("", root_view),
    path("favicon.ico", favicon_view),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/", include("apps.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
