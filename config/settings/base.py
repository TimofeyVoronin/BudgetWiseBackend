import os
from datetime import timedelta
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


SECRET_KEY = env("SECRET_KEY", default="django-insecure-budgetwise-dev-secret-key")


METRICS_ACCESS_TOKEN = env("METRICS_ACCESS_TOKEN", default="")


EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="BudgetWise <noreply@budgetwise.local>",
)

FRONTEND_EMAIL_VERIFY_URL = env(
    "FRONTEND_EMAIL_VERIFY_URL",
    default="http://app.budgetwise.localhost:5173/auth/verify-email",
)

EMAIL_CONFIRMATION_TOKEN_TIMEOUT_SECONDS = env.int(
    "EMAIL_CONFIRMATION_TOKEN_TIMEOUT_SECONDS",
    default=60 * 60 * 24,
)

EMAIL_CONFIRMATION_TOKEN_SALT = env(
    "EMAIL_CONFIRMATION_TOKEN_SALT",
    default="budgetwise.email-confirmation",
)

REGISTRATION_REQUIRE_EMAIL_CONFIRMATION = env.bool(
    "REGISTRATION_REQUIRE_EMAIL_CONFIRMATION",
    default=False,
)

FRONTEND_PASSWORD_RESET_URL = env(
    "FRONTEND_PASSWORD_RESET_URL",
    default="http://app.budgetwise.localhost:5173/auth/reset-password",
)

PASSWORD_RESET_TOKEN_TIMEOUT_SECONDS = env.int(
    "PASSWORD_RESET_TOKEN_TIMEOUT_SECONDS",
    default=60 * 60,
)

PASSWORD_RESET_TOKEN_BYTES = env.int(
    "PASSWORD_RESET_TOKEN_BYTES",
    default=32,
)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)


DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

DRF_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
]

THIRD_PARTY_APPS = [
    "corsheaders",
]

PROJECT_APPS = [
    "apps.users.apps.UsersConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.common.apps.CommonConfig",
]

INSTALLED_APPS = DJANGO_APPS + DRF_APPS + THIRD_PARTY_APPS + PROJECT_APPS


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.common.metrics.PrometheusMetricsMiddleware",
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

WSGI_APPLICATION = "config.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="finance_db"),
        "USER": env("POSTGRES_USER", default="finance_user"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="finance_password"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}


AUTH_USER_MODEL = "users.User"


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_THROTTLE_RATE = env("LOGIN_THROTTLE_RATE", default="5/min")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "DATE_FORMAT": "%Y-%m-%d",
    "DEFAULT_THROTTLE_RATES": {
        "login": LOGIN_THROTTLE_RATE,
    },
}


SPECTACULAR_SETTINGS = {
    "TITLE": "BudgetWiseBackend API",
    "DESCRIPTION": (
        "OpenAPI-документация backend-части прогрессивного веб-приложения "
        "для управления личными финансами."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "filter": True,
    },
    "TAGS": [
        {
            "name": "health",
            "description": "Служебные endpoints состояния backend-сервиса.",
        },
        {
            "name": "users",
            "description": "Endpoints профиля пользователя и администрирования пользователей.",
        },
        {
            "name": "finance",
            "description": "Endpoints финансового модуля: категории и операции.",
        },
    ],
}


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


LOGGING_FORMATTERS = {
    "simple": {
        "format": "%(levelname)s %(asctime)s %(name)s: %(message)s",
    },
    "verbose": {
        "format": (
            "%(levelname)s %(asctime)s %(name)s "
            "%(module)s:%(lineno)d %(message)s"
        ),
    },
}