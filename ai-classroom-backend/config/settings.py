from pathlib import Path
import os
import logging.config
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================================
# ENVIRONMENT CONFIGURATION WITH VALIDATION
# ============================================================================

class Settings(BaseSettings):
    """
    Production-ready settings with validation.
    Uses pydantic-settings for type checking and validation.
    """
    # Django
    SECRET_KEY: str = Field(default="dev-secret-key")
    DEBUG: bool = Field(default=True)  # Changed to True for easier local testing
    ENVIRONMENT: str = Field(default="development")
    ALLOWED_HOSTS: str = Field(default="127.0.0.1,localhost")
    
    # CORS
    CORS_ALLOWED_ORIGINS: str = Field(default="http://localhost:5173,http://127.0.0.1:5173")
    
    # OLLAMA Configuration
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OLLAMA_MODEL_PRIMARY: str = Field(default="qwen2.5:7b")
    OLLAMA_MODEL_CODER: str = Field(default="qwen2.5-coder:7b")
    OLLAMA_EMBED_MODEL: str = Field(default="")
    OLLAMA_EMBED_KEEP_ALIVE: str = Field(default="30m")
    OLLAMA_TIMEOUT: int = Field(default=300)
    
    # Gemini Configuration (optional)
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL_PRIMARY: str = Field(default="gemini-2.5-flash")
    GEMINI_MODEL_CODER: str = Field(default="gemini-2.5-pro")
    
    # Other services
    INSTITUTE_EMAIL_DOMAIN: str = Field(default="iiitdwd.ac.in")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")
    SENTRY_DSN: str = Field(default="")
    
    # Cache timeouts (in seconds)
    CACHE_TIMEOUT: int = Field(default=300)
    ANSWER_CACHE_TIMEOUT: int = Field(default=300)
    SEARCH_CACHE_TIMEOUT: int = Field(default=1800)
    
    # Security
    SECURE_SSL_REDIRECT: bool = Field(default=False)
    SESSION_COOKIE_SECURE: bool = Field(default=False)
    CSRF_COOKIE_SECURE: bool = Field(default=False)
    SECURE_HSTS_SECONDS: int = Field(default=0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = Field(default=False)
    SECURE_HSTS_PRELOAD: bool = Field(default=False)
    
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v):
        if v not in ["development", "staging", "production"]:
            raise ValueError(f"ENVIRONMENT must be one of: development, staging, production. Got: {v}")
        return v
    
    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, bool):
            return v
        return v.lower() in ("true", "1", "yes")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Load validated settings
settings = Settings(_env_file=BASE_DIR.parent / ".env", _case_sensitive=False)

# Ensure SECRET_KEY is set for production
if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == "dev-secret-key":
    raise ValueError(
        "CRITICAL: SECRET_KEY must be set in .env for production environment. "
        "Generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    )

SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ENVIRONMENT = settings.ENVIRONMENT
ALLOWED_HOSTS = [h.strip() for h in settings.ALLOWED_HOSTS.split(",")]

# ============================================================================
# DJANGO CORE SETTINGS
# ============================================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "apps.users",
    "apps.courses",
    "apps.assignments",
    "apps.submissions",
    "apps.chat",
    "apps.ai_service",
    "apps.analytics",
]

if DEBUG:
    INSTALLED_APPS += ["django_extensions"]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.RequestLoggingMiddleware",
    "config.middleware.ErrorHandlingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

if settings.ENVIRONMENT == "production":
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ============================================================================
# AUTHENTICATION & SECURITY
# ============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# SSL/HTTPS Security
SECURE_SSL_REDIRECT = settings.SECURE_SSL_REDIRECT
SESSION_COOKIE_SECURE = settings.SESSION_COOKIE_SECURE
CSRF_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE
SECURE_HSTS_SECONDS = settings.SECURE_HSTS_SECONDS
SECURE_HSTS_INCLUDE_SUBDOMAINS = settings.SECURE_HSTS_INCLUDE_SUBDOMAINS
SECURE_HSTS_PRELOAD = settings.SECURE_HSTS_PRELOAD

# ============================================================================
# INTERNATIONALIZATION
# ============================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Calcutta"
USE_I18N = True
USE_TZ = True

# ============================================================================
# STATIC FILES & MEDIA
# ============================================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ============================================================================
# DEFAULT MODEL & AUTH
# ============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"
SITE_ID = 1

# ============================================================================
# CORS CONFIGURATION
# ============================================================================

CORS_ALLOWED_ORIGINS = [f"http://{host}" for host in ALLOWED_HOSTS if host != "*"]
CORS_ALLOWED_ORIGINS += [f"https://{host}" for host in ALLOWED_HOSTS if host != "*"]

if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False

# ============================================================================
# REST FRAMEWORK CONFIGURATION
# ============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "50/hour",
        "user": "500/hour",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}

# ============================================================================
# SWAGGER/OPENAPI DOCUMENTATION
# ============================================================================

SPECTACULAR_SETTINGS = {
    "TITLE": "AI Classroom API",
    "DESCRIPTION": "Local-first AI classroom platform with RAG chat and assignments",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SPECTACULAR_DEFAULTS": {
        "SUMMARY": "Auto-generated endpoint",
    },
}

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

CELERY_BROKER_URL = settings.CELERY_BROKER_URL
CELERY_RESULT_BACKEND = settings.CELERY_RESULT_BACKEND
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60

# NO-REDIS DEVELOPMENT MODE
# This makes .delay() calls run synchronously in the main thread
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ============================================================================
# CACHING CONFIGURATION
# ============================================================================

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": settings.REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "redis.StrictRedis",
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
        "KEY_PREFIX": f"aiclass_{ENVIRONMENT}",
        "TIMEOUT": settings.CACHE_TIMEOUT,
    }
}

# Fallback to in-memory cache if Redis is unavailable
try:
    import redis
    redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
except Exception:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "aiclass-cache",
            "OPTIONS": {
                "MAX_ENTRIES": 10000,
            },
        }
    }

# ============================================================================
# STRUCTURED JSON LOGGING
# ============================================================================

LOGGING_CONFIG = None

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if not DEBUG else "standard",
            "level": "INFO",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json",
            "level": "INFO",
        },
        "ai_service_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "ai_service.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json",
            "level": "DEBUG",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.ai_service": {
            "handlers": ["console", "ai_service_file"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "apps.courses": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING)

# ============================================================================
# SERVICE CONFIGURATION (Ollama, Gemini, etc.)
# ============================================================================

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL_PRIMARY = settings.OLLAMA_MODEL_PRIMARY
OLLAMA_MODEL_CODER = settings.OLLAMA_MODEL_CODER
OLLAMA_EMBED_MODEL = settings.OLLAMA_EMBED_MODEL
OLLAMA_EMBED_KEEP_ALIVE = settings.OLLAMA_EMBED_KEEP_ALIVE
OLLAMA_TIMEOUT = settings.OLLAMA_TIMEOUT

GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL_PRIMARY = settings.GEMINI_MODEL_PRIMARY
GEMINI_MODEL_CODER = settings.GEMINI_MODEL_CODER

INSTITUTE_EMAIL_DOMAIN = settings.INSTITUTE_EMAIL_DOMAIN

# ============================================================================
# CACHE TIMEOUTS FOR SERVICES
# ============================================================================

CACHE_TIMEOUT = settings.CACHE_TIMEOUT
ANSWER_CACHE_TIMEOUT = settings.ANSWER_CACHE_TIMEOUT
SEARCH_CACHE_TIMEOUT = settings.SEARCH_CACHE_TIMEOUT

# ============================================================================
# SENTRY ERROR TRACKING (Optional)
# ============================================================================

if settings.SENTRY_DSN and ENVIRONMENT != "development":
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1 if ENVIRONMENT == "production" else 1.0,
        send_default_pii=False,
        environment=ENVIRONMENT,
    )
