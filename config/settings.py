"""
Django settings for LinkSheet.

Environment variables (all required in production, optional in dev):
  DJANGO_SECRET_KEY       — Django secret key (MUST be unique per deployment)
  DJANGO_DEBUG            — "True" for dev, "False" for production
  DJANGO_ALLOWED_HOSTS    — Comma-separated hostnames, e.g. "myapp.com,www.myapp.com"
  GOOGLE_REDIRECT_URI     — OAuth callback URL (must match Google Cloud Console)
  FIELD_ENCRYPTION_KEY    — Fernet key for encrypting stored OAuth tokens
  CELERY_BROKER_URL       — Redis URL for Celery broker
  CELERY_RESULT_BACKEND   — Where Celery stores task results (default: django-db)
"""
import os
from pathlib import Path
import platform

import dj_database_url

# ─────────────────────────────────────────────────────────────────────────────
# 1. Environment Setup
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# 2. Security Settings
# ─────────────────────────────────────────────────────────────────────────────

# ⚠️  PRODUCTION: Set DJANGO_SECRET_KEY in your environment — NEVER use this
#                 fallback in production. It is here only for local dev.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-migdv^6jll#jgoho9xtlf&#k464r_v-%s7wt@lir-n!aww6c96"
)

# ⚠️  PRODUCTION: Set DJANGO_DEBUG=False. Running with DEBUG=True leaks stack
#                 traces and internal paths to end users.
DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

# In production, set ALLOWED_HOSTS via env-var (comma-separated).
# Example: DJANGO_ALLOWED_HOSTS="myapp.com,www.myapp.com"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. Production Security Headers
#    Automatically enforced when DEBUG=False. Safe to leave in settings.
# ─────────────────────────────────────────────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000           # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
else:
    # Allow HTTP in development (required for Google OAuth local testing).
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    # Accept scope changes (Google may return previously granted scopes).
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False

# ─────────────────────────────────────────────────────────────────────────────
# 4. Application Definition
# ─────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "django_celery_results",

    # Local
    "sheets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Injects google_profile_pic into every template context.
                "sheets.context_processors.google_profile",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ─────────────────────────────────────────────────────────────────────────────
# 5. Database
#    PRODUCTION: Set DATABASE_URL env-var to a PostgreSQL URI
#    (e.g., postgres://user:pass@host:5432/dbname).
#    DEVELOPMENT: If DATABASE_URL is not set, defaults to local SQLite.
# ─────────────────────────────────────────────────────────────────────────────
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. Password Validation
# ─────────────────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─────────────────────────────────────────────────────────────────────────────
# 7. Internationalization
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────────────────────
# 8. Static Files
#    STATIC_ROOT: where collectstatic copies files for production serving.
#    STATICFILES_DIRS: additional directories searched during development.
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Only include the /static source dir if it actually exists (avoids errors
# when the directory hasn't been created yet locally).
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

# ─────────────────────────────────────────────────────────────────────────────
# 9. Auth / Login
# ─────────────────────────────────────────────────────────────────────────────
LOGIN_URL = "/google/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# ─────────────────────────────────────────────────────────────────────────────
# 10. Logging
#     Structured logging for all environments. In dev (DEBUG=True) the
#     "sheets" logger emits DEBUG-level messages to the console. In prod
#     only WARNING+ is emitted to prevent log flooding.
# ─────────────────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {module}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            # Logs 4xx/5xx responses — always on even in prod.
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "sheets": {
            "handlers": ["console"],
            # DEBUG in development so you can trace ORM queries & sync steps.
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# 11. Google API Settings
# ─────────────────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_CLIENT_SECRET_FILE = BASE_DIR / "linksheet.json"  # Local fallback
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# OAuth callback URI — must match exactly what is registered in Google Cloud Console.
# ⚠️  PRODUCTION: Set GOOGLE_REDIRECT_URI to your production callback URL.
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/google/callback/"
)

# ─────────────────────────────────────────────────────────────────────────────
# 12. Token Encryption (Fernet)
#     Used to encrypt/decrypt OAuth access & refresh tokens stored in the DB.
#
#     ⚠️  PRODUCTION: Generate a unique key and set it as an env-var — NEVER
#                     commit a real encryption key to version control.
#     Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# ─────────────────────────────────────────────────────────────────────────────
FIELD_ENCRYPTION_KEY = os.environ.get(
    "FIELD_ENCRYPTION_KEY",
    "2QDAbCXbYfqJyEJcaUiEiHvNnUS__9Urm8eNoAenMJ8="
)

# ─────────────────────────────────────────────────────────────────────────────
# 13. Celery
#     The "solo" pool is required on Windows (no fork support).
#     In Linux/Mac production environments the default prefork pool is used.
# ─────────────────────────────────────────────────────────────────────────────
if platform.system() == "Windows":
    CELERY_WORKER_POOL = "solo"

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "django-db")