"""
Django settings.

Single module rather than a base/dev/prod package — there is one deployment target,
so splitting it would be indirection without benefit (ADR-0006).

Every environment-dependent value is read from the environment. Required values are
validated at import time by `_required()`, so a misconfigured deployment fails at
startup with a clear message rather than at the first request that happens to need it.
"""

from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development convenience only. `override=False` is the important part:
# real environment variables always win, so a stray .env inside a container
# cannot quietly shadow the secrets the platform injected.
load_dotenv(BASE_DIR / ".env", override=False)


# --------------------------------------------------------------------------
# Environment helpers
# --------------------------------------------------------------------------


class ImproperlyConfigured(Exception):
    """Raised at startup when a required environment variable is missing."""


def _required(name: str) -> str:
    """Read a required env var, failing fast with an actionable message."""
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(
            f"Missing required environment variable: {name}. "
            f"Copy backend/.env.example to backend/.env and set it."
        )
    return value


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    """Read an int env var, falling back to the default if unset or malformed."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str = "") -> list[str]:
    """Parse a comma-separated env var into a list, dropping empty entries."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

DEBUG = _bool("DJANGO_DEBUG", False)

# Required in every environment. In DEBUG a fallback keeps first-run friction low;
# in production the absence of a real key is fatal.
if DEBUG:
    SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-not-for-production")
else:
    SECRET_KEY = _required("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Fly.io terminates TLS at the edge and forwards this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "django_filters",
    "rest_framework",
    "films",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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


# --------------------------------------------------------------------------
# Database (ADR-0004: SQLite — 350 films / 2,214 locations / ~1.5 MB)
# --------------------------------------------------------------------------

# Relative locally; on Fly.io this points at /data/db.sqlite3, a mounted
# persistent volume, so the sync command's writes survive restarts (ADR-0005).
DATABASE_PATH = os.getenv("DATABASE_PATH", "db.sqlite3")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": (
            DATABASE_PATH
            if os.path.isabs(DATABASE_PATH)
            else BASE_DIR / DATABASE_PATH
        ),
        "OPTIONS": {
            # WAL lets the read-only API serve requests while a sync writes.
            "init_command": "PRAGMA journal_mode=WAL;",
            "transaction_mode": "IMMEDIATE",
        },
    }
}


# --------------------------------------------------------------------------
# DataSF Socrata API (ADR-0003: scheduled batch pull, not a live proxy)
# --------------------------------------------------------------------------

SOCRATA = {
    "BASE_URL": os.getenv("SOCRATA_BASE_URL", "https://data.sfgov.org"),
    "DATASET_ID": os.getenv("SOCRATA_DATASET_ID", "yitu-d5am"),
    # Optional. Unauthenticated requests are throttled harder but work at this volume.
    "APP_TOKEN": os.getenv("SOCRATA_APP_TOKEN", ""),
    "TIMEOUT_SECONDS": _int("SOCRATA_TIMEOUT_SECONDS", 15),
    "MAX_RETRIES": _int("SOCRATA_MAX_RETRIES", 3),
    "PAGE_SIZE": _int("SOCRATA_PAGE_SIZE", 1000),
}


# --------------------------------------------------------------------------
# REST framework
# --------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    # Read-only public API; no auth and no throttling by deliberate choice (ADR-0006).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# The SPA is served from a different origin (ADR-0005), so it needs explicit CORS.
CORS_ALLOWED_ORIGINS = _csv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_METHODS = ["GET", "OPTIONS"]


# --------------------------------------------------------------------------
# Logging (ADR-0006: stdlib logging, no structlog dependency)
# --------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname:<8} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        # Application logs: ingestion progress, outgoing-call attempts, request errors.
        "films": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}


# --------------------------------------------------------------------------
# Static files / i18n
# --------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
