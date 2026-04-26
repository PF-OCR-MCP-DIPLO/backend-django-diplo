import os
from pathlib import Path
from urllib.parse import urlparse

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
DEFAULT_SECRET_KEY = "django-insecure-dev-only-change-me"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEFAULT_SECRET_KEY)
if not DEBUG and SECRET_KEY == DEFAULT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be configured when DJANGO_DEBUG=0."
    )

default_allowed_hosts = "localhost,127.0.0.1" if DEBUG else ""
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", default_allowed_hosts).split(",")
    if host.strip()
]
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must be configured when DJANGO_DEBUG=0."
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.api",
    "apps.documents",
    "apps.extraction",
    "apps.processing",
    "apps.common",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.request_id.RequestIdMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "MCP_back.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "MCP_back.wsgi.application"


def _database_config():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        if DEBUG:
            return {
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": BASE_DIR / "db.sqlite3",
                }
            }
        raise ImproperlyConfigured(
            "DATABASE_URL must be configured when DJANGO_DEBUG=0."
        )
    parsed = urlparse(database_url)
    if parsed.scheme in {"sqlite", "sqlite3"}:
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": parsed.path or str(BASE_DIR / "db.sqlite3"),
            }
        }
    engine_map = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
    }
    engine = engine_map.get(parsed.scheme)
    if not engine:
        raise ImproperlyConfigured("Unsupported DATABASE_URL scheme.")
    return {
        "default": {
            "ENGINE": engine,
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
    }


DATABASES = _database_config()

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "es-co"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "America/Bogota")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173" if DEBUG else "",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_HEADERS = (*default_headers, "x-api-key")
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS)
    ).split(",")
    if origin.strip()
]
PROCESS_JOBS_ASYNC = os.environ.get("PROCESS_JOBS_ASYNC", "1") == "1"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "apps.api.exception_handlers.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "documents_upload": "20/min",
        "jobs_process": "20/min",
        "jobs_export": "30/min",
        "processing_settings": "60/min",
    },
}

API_KEY = os.environ.get("API_KEY", "")
ALLOW_OPEN_API_FOR_DEV = (
    os.environ.get("ALLOW_OPEN_API_FOR_DEV", "1" if DEBUG else "0") == "1"
)
if not DEBUG and not API_KEY:
    raise ImproperlyConfigured("API_KEY must be configured when DJANGO_DEBUG=0.")
if not DEBUG and ALLOW_OPEN_API_FOR_DEV:
    raise ImproperlyConfigured(
        "ALLOW_OPEN_API_FOR_DEV cannot be enabled when DJANGO_DEBUG=0."
    )

DOCX_MAX_UPLOAD_BYTES = int(
    os.environ.get("DOCX_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
)
DOCX_MAX_IMAGES = int(os.environ.get("DOCX_MAX_IMAGES", "50"))
EXTRACTED_IMAGE_MAX_BYTES = int(
    os.environ.get("EXTRACTED_IMAGE_MAX_BYTES", str(5 * 1024 * 1024))
)
MCP_ENABLE_MUTATIONS = os.environ.get("MCP_ENABLE_MUTATIONS", "0") == "1"

# Enables deterministic stub OCR/LLM providers for E2E and local demos.
STUB_PROVIDERS = os.environ.get("STUB_PROVIDERS", "0") == "1"

OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "ollama_vision")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama_text")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e2b")
OLLAMA_VISION_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "gemma4:e2b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "320"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))
LLM_RETRY_DELAY = int(os.environ.get("LLM_RETRY_DELAY", "2"))
MAX_OCR_CHARS_FOR_LLM = int(os.environ.get("MAX_OCR_CHARS_FOR_LLM", "12000"))
TESSERACT_TIMEOUT_SECONDS = int(os.environ.get("TESSERACT_TIMEOUT_SECONDS", "90"))

SPECTACULAR_SETTINGS = {
    "TITLE": "Diplo OCR/LLM API",
    "DESCRIPTION": "API para carga de documentos, procesamiento OCR/LLM, logs, exportación y configuración.",
    "VERSION": os.environ.get("APP_VERSION", "0.1.0"),
    "SERVE_INCLUDE_SCHEMA": False,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging.RequestIdLogFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(levelname)s %(asctime)s [%(name)s] [req:%(request_id)s] %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        }
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

SECURE_SSL_REDIRECT = (
    os.environ.get("SECURE_SSL_REDIRECT", "1" if not DEBUG else "0") == "1"
)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0")
)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
