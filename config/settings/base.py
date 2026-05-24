import os
from datetime import timedelta
from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


SECRET_KEY = env("SECRET_KEY", default="django-insecure-budgetwise-dev-secret-key")


METRICS_ACCESS_TOKEN = env("METRICS_ACCESS_TOKEN", default="")


PROVERKACHEKA_API_TOKEN = env("PROVERKACHEKA_API_TOKEN", default="")
PROVERKACHEKA_API_URL = env(
    "PROVERKACHEKA_API_URL",
    default="https://proverkacheka.com/api/v1/check/get",
)
PROVERKACHEKA_TIMEOUT_SECONDS = env.int(
    "PROVERKACHEKA_TIMEOUT_SECONDS",
    default=10,
)
PROVERKACHEKA_ENABLED = env.bool(
    "PROVERKACHEKA_ENABLED",
    default=False,
)


CURRENCY_RATES_ENABLED = env.bool(
    "CURRENCY_RATES_ENABLED",
    default=True,
)
CURRENCY_RATES_CACHE_SECONDS = env.int(
    "CURRENCY_RATES_CACHE_SECONDS",
    default=15 * 60,
)
CURRENCY_RATES_FAILURE_CACHE_SECONDS = env.int(
    "CURRENCY_RATES_FAILURE_CACHE_SECONDS",
    default=5 * 60,
)
CURRENCY_RATES_TIMEOUT_SECONDS = env.float(
    "CURRENCY_RATES_TIMEOUT_SECONDS",
    default=2.0,
)
CURRENCY_FIAT_RATES_URL = env(
    "CURRENCY_FIAT_RATES_URL",
    default="https://www.cbr.ru/scripts/XML_daily.asp",
)
CURRENCY_CRYPTO_RATES_URL = env(
    "CURRENCY_CRYPTO_RATES_URL",
    default="https://api.coingecko.com/api/v3/simple/price",
)


# PWA and push notifications
PWA_PUSH_SUBSCRIPTIONS_ENABLED = env.bool(
    "PWA_PUSH_SUBSCRIPTIONS_ENABLED",
    default=True,
)
PWA_PUSH_SEND_ENABLED = env.bool(
    "PWA_PUSH_SEND_ENABLED",
    default=False,
)
PWA_PUSH_PROVIDER = env(
    "PWA_PUSH_PROVIDER",
    default="web_push",
)
PWA_VAPID_PUBLIC_KEY = env(
    "PWA_VAPID_PUBLIC_KEY",
    default="",
)
PWA_VAPID_PRIVATE_KEY = env(
    "PWA_VAPID_PRIVATE_KEY",
    default="",
)
PWA_VAPID_SUBJECT = env(
    "PWA_VAPID_SUBJECT",
    default="mailto:noreply@budgetwise.local",
)
PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER = env.int(
    "PWA_MAX_PUSH_SUBSCRIPTIONS_PER_USER",
    default=10,
)
PWA_BACKGROUND_SYNC_ENABLED = env.bool(
    "PWA_BACKGROUND_SYNC_ENABLED",
    default=True,
)
PWA_BACKGROUND_SYNC_RETRY_SECONDS = env.int(
    "PWA_BACKGROUND_SYNC_RETRY_SECONDS",
    default=30,
)
PWA_PUSH_TTL_SECONDS = env.int(
    "PWA_PUSH_TTL_SECONDS",
    default=60,
)


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
    "apps.pwa.apps.PwaConfig",
    "apps.common.apps.CommonConfig",
]

INSTALLED_APPS = DJANGO_APPS + DRF_APPS + THIRD_PARTY_APPS + PROJECT_APPS


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.common.monitoring.metrics.PrometheusMetricsMiddleware",
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

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

USER_PROFILE_AVATAR_MAX_SIZE_BYTES = env.int(
    "USER_PROFILE_AVATAR_MAX_SIZE_BYTES",
    default=5 * 1024 * 1024,
)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_THROTTLE_RATE = env("LOGIN_THROTTLE_RATE", default="5/min")

FORGOT_PASSWORD_IP_THROTTLE_RATE = env(
    "FORGOT_PASSWORD_IP_THROTTLE_RATE",
    default="10/min",
)

FORGOT_PASSWORD_EMAIL_THROTTLE_RATE = env(
    "FORGOT_PASSWORD_EMAIL_THROTTLE_RATE",
    default="3/hour",
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.classes.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.errors.handlers.custom_exception_handler",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "DATE_FORMAT": "%Y-%m-%d",
    "DEFAULT_THROTTLE_RATES": {
        "login": LOGIN_THROTTLE_RATE,
        "forgot_password_ip": FORGOT_PASSWORD_IP_THROTTLE_RATE,
        "forgot_password_email": FORGOT_PASSWORD_EMAIL_THROTTLE_RATE,
    },
    "URL_FORMAT_OVERRIDE": None,
}


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "budgetwise-dashboard-cache",
        "TIMEOUT": 300,
    }
}


SPECTACULAR_SETTINGS = {
    "TITLE": "BudgetWiseBackend API",
    "DESCRIPTION": (
        "OpenAPI-документация серверной части прогрессивного веб-приложения "
        "для управления личными финансами.\n\n"
        "API предоставляет endpoints для регистрации и аутентификации пользователей, "
        "управления профилем, финансовыми счетами, бюджетами, тегами операций, финансовыми целями, уведомлениями, финансовыми калькуляторами, регулярными операциями, планируемыми операциями, "
        "категориями, операциями, агрегированными данными главного "
        "дашборда и служебного мониторинга.\n\n"   
        "Авторизация защищённых endpoints выполняется через JWT Bearer token. "
        "Для ручной проверки в Swagger UI сначала выполните login-запрос, "
        "получите access token и передайте его в Authorize в формате: "
        "Bearer <access_token>."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "TransactionTypeEnum": [
            ("income", "Доход"),
            ("expense", "Расход"),
        ],
        "GoalStatusEnum": [
            ("active", "Активна"),
            ("completed", "Завершена"),
            ("archived", "В архиве"),
            ("cancelled", "Отменена"),
        ],
        "GoalPriorityEnum": [
            ("high", "Высокий"),
            ("medium", "Средний"),
            ("low", "Низкий"),
        ],
        "GoalCategoryEnum": [
            ("savings", "Накопления"),
            ("housing", "Жильё"),
            ("transport", "Транспорт"),
            ("travel", "Путешествия"),
            ("other", "Другое"),
        ],
        "NotificationChannelEnum": [
            ("in_app", "In-app"),
            ("email", "Email"),
            ("push", "Push"),
            ("sms", "SMS"),
        ],
        "NotificationTypeEnum": [
            ("operation", "Операции"),
            ("goal", "Цели"),
            ("budget", "Бюджет"),
            ("system", "Система"),
            ("security", "Безопасность"),
            ("marketing", "Маркетинг и акции"),
        ],
        "NotificationDeliveryStatusEnum": [
            ("delivered", "Доставлено"),
            ("failed", "Ошибка доставки"),
            ("pending", "Ожидает доставки"),
            ("unavailable", "Канал недоступен"),
        ],
        "NotificationIconToneEnum": [
            ("primary", "Основной"),
            ("success", "Успех"),
            ("warning", "Предупреждение"),
            ("error", "Ошибка"),
            ("info", "Информация"),
        ],
        "NotificationEntityKindEnum": [
            ("transaction", "Операция"),
            ("goal", "Цель"),
            ("budget", "Бюджет"),
        ],
        "RecurringFrequencyEnum": [
            ("daily", "Ежедневно"),
            ("weekly", "Еженедельно"),
            ("monthly", "Ежемесячно"),
            ("yearly", "Ежегодно"),
        ],
        "RecurringStatusEnum": [
            ("active", "Активна"),
            ("paused", "На паузе"),
            ("completed", "Завершена"),
            ("error", "Ошибка"),
        ],
        "RecurringChargeStatusEnum": [
            ("success", "Выполнено"),
            ("failed", "Ошибка"),
            ("skipped", "Пропущено"),
        ],
        "PlannedStatusEnum": [
            ("pending", "Ожидает"),
            ("confirmed", "Подтверждена"),
            ("cancelled", "Отменена"),
            ("converted", "Конвертирована"),
            ("overdue", "Просрочена"),
        ],
        "AccountTypeEnum": [
            ("card", "Банковская карта"),
            ("debit", "Дебетовая карта"),
            ("savings", "Накопительный"),
            ("cash", "Наличные"),
            ("credit", "Кредитный"),
            ("other", "Другое"),
        ],
        "BudgetKindEnum": [
            ("expense", "Расходный"),
            ("income", "Доходный"),
        ],
        "BudgetPeriodTypeEnum": [
            ("month", "Месяц"),
            ("quarter", "Квартал"),
            ("year", "Год"),
        ],
        "BudgetCategoryGroupEnum": [
            ("main", "Основной бюджет"),
            ("family", "Семейный"),
            ("personal", "Личный"),
        ],
        "BudgetUsageStatusEnum": [
            ("normal", "Норма"),
            ("warning", "Близко к лимиту"),
            ("exceeded", "Превышен"),
        ],
        "TransactionTemplateStatusEnum": [
            ("active", "Активный"),
            ("archived", "В архиве"),
        ],
        "TransactionTemplateIconToneEnum": [
            ("primary", "Основной"),
            ("success", "Успех"),
            ("warning", "Предупреждение"),
            ("info", "Информация"),
        ],
        "BudgetNotificationChannelEnum": [
            ("email", "Email"),
            ("push", "Push"),
            ("in_app", "In-app"),
        ],
        "BudgetNotificationEventGroupEnum": [
            ("budget", "Бюджет"),
            ("goal", "Цель накопления"),
        ],
        "BudgetNotificationEventTypeEnum": [
            ("budget_near_limit", "Бюджет: приближение к лимиту"),
            ("budget_exceeded", "Бюджет: превышение лимита"),
            ("budget_back_to_normal", "Бюджет: возврат в норму"),
            ("goal_milestone", "Цель: достигнут промежуточный рубеж"),
            ("goal_reached", "Цель: цель выполнена"),
            ("goal_lagging", "Цель: отставание от плана"),
        ],
        "BudgetNotificationDeliveryStatusEnum": [
            ("available", "Доступен"),
            ("not_configured", "Не настроен"),
            ("disabled", "Отключён"),
        ],
        "BudgetNotificationEventStatusEnum": [
            ("generated", "Сформировано"),
            ("delivered", "Доставлено"),
            ("skipped", "Пропущено"),
        ],

        "CalculatorIdEnum": [
            ("credit", "Кредит"),
            ("mortgage", "Ипотека"),
            ("installment", "Рассрочка"),
            ("deposit", "Вклад"),
            ("pension", "Пенсия"),
            ("inflation", "Инфляция"),
        ],
        "LoanPaymentTypeEnum": [
            ("annuity", "Аннуитетный"),
            ("differentiated", "Дифференцированный"),
        ],
        "DepositCapitalizationEnum": [
            ("none", "Нет"),
            ("monthly", "Ежемесячно"),
            ("quarterly", "Ежеквартально"),
            ("yearly", "Ежегодно"),
        ],
        "DepositTopUpEnum": [
            ("none", "Нет"),
            ("monthly", "Ежемесячно"),
        ],
        "FinancialCalendarEventTypeEnum": [
            ("income", "Доход"),
            ("expense", "Расход"),
            ("transfer", "Перевод"),
            ("reminder", "Напоминание"),
        ],
        "FinancialCalendarEventStatusEnum": [
            ("confirmed", "Факт"),
            ("pending", "План"),
        ],
        "FinancialCalendarRiskLevelEnum": [
            ("safe", "Безопасно"),
            ("caution", "Внимание"),
            ("risk", "Риск кассового разрыва"),
        ],
        "PwaPushProviderEnum": [
            ("web_push", "Web Push"),
        ],
    },
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "filter": True,
        "docExpansion": "none",
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 2,
        "operationsSorter": "alpha",
        "tagsSorter": "alpha",
        "tryItOutEnabled": True,
    },
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
        "expandResponses": "200,201",
        "pathInMiddlePanel": True,
    },
    "TAGS": [
        {
            "name": "auth",
            "description": (
                "Регистрация, вход, обновление JWT-токена, подтверждение email "
                "и восстановление пароля."
            ),
        },
        {
            "name": "users",
            "description": (
                "Endpoints профиля пользователя и административного управления "
                "пользователями."
            ),
        },
        {
            "name": "users-profile",
            "description": (
                "Страница профиля текущего пользователя: получение и обновление "
                "ФИО, телефона, города, краткого описания и статусов подтверждения "
                "контактных данных."
            ),
        },
        {
            "name": "finance-accounts",
            "description": (
                "Финансовые счета: список, создание, редактирование, архивирование, "
                "сводка балансов, история операций по счёту и справочники для формы."
            ),
        },
        {
            "name": "finance-budgets",
            "description": (
                "Бюджеты и лимиты: список, создание, редактирование, удаление, "
                "пауза, возобновление, расчёт прогресса, предупреждения, "
                "детальная статистика и справочники для формы."
            ),
        },
        {
            "name": "finance-goals",
            "description": (
                "Финансовые цели: список, создание, редактирование, архивирование, "
                "завершение, отмена, восстановление, сводка прогресса, история "
                "пополнений и справочники для формы."
            ),
        },
        {
            "name": "finance-notifications",
            "description": (
                "Центр уведомлений: список, просмотр, фильтрация, отметка "
                "как прочитанное/непрочитанное, архивация, восстановление, "
                "сводка, справочники, настройки каналов, типов уведомлений "
                "и тихих часов."
            ),
        },
        {
            "name": "finance-budget-notifications",
            "description": (
                "Настройки уведомлений о бюджетах и целях: включение, пороги, "
                "типы событий, каналы доставки, защита от дублей, предпросмотр "
                "и тестовая отправка. На текущем этапе реально доступен in-app канал."
            ),
        },
        {
            "name": "finance-currencies",
            "description": (
                "Управление валютами пользователя: список доступных валют, "
                "каталог системных валют, пользовательские валюты, основная валюта, "
                "видимость в интерфейсе и select-options для финансовых форм."
            ),
        },
        {
            "name": "finance-calculators",
            "description": (
                "Финансовые калькуляторы без сохранения результата в базе: кредит, "
                "ипотека, рассрочка, вклад, пенсионные накопления и инфляция. "
                "Endpoints возвращают значения по умолчанию, выполняют расчёт и "
                "показывают ошибки валидации входных параметров."
            ),
        },
        {
            "name": "finance-recurring-transactions",
            "description": (
                "Регулярные операции: список, создание, редактирование, удаление, "
                "пауза, возобновление, завершение, справочники, сводка, история "
                "списаний и проверка расписания."
            ),
        },
        {
            "name": "finance-planned-transactions",
            "description": (
                "Планируемые операции: будущие доходы и расходы, список, "
                "создание, редактирование, отмена, подтверждение, "
                "конвертация в фактические операции, календарь и прогноз баланса."
            ),
        },
        {
            "name": "finance-categories",
            "description": (
                "Финансовые категории: список, создание, дерево категорий, "
                "избранное, архивирование, drag and drop порядок и подсказки "
                "категорий по описанию операции."
            ),
        },
        {
            "name": "finance-tags",
            "description": (
                "Теги операций: централизованное управление тегами, группы, "
                "поиск, создание, редактирование, удаление, видимость в формах "
                "и справочники для выбора тегов в операциях и отчётах."
            ),
        },
        {
            "name": "finance-transaction-templates",
            "description": (
                "Шаблоны операций: сохранённые заготовки доходов и расходов, "
                "создание, редактирование, архивирование, дублирование, "
                "черновик применения и создание операции из шаблона."
            ),
        },
        {
            "name": "finance-transactions",
            "description": (
                "Финансовые операции: список, фильтрация, пагинация, создание, "
                "обновление, удаление и экспорт операций в CSV, XLSX и PDF."
            ),
        },
        {
            "name": "finance-receipts",
            "description": (
                "Фискальные чеки: импорт данных из QR-кода, защита от дублей, "
                "сопоставление позиций с категориями и создание одной или нескольких "
                "финансовых операций из исходного чека."
            ),
        },
        {
            "name": "finance-dashboard",
            "description": (
                "Главный дашборд: агрегированные показатели по счетам, доходам, "
                "расходам, последним операциям и категориям расходов."
            ),
        },
        {
            "name": "finance-sync",
            "description": (
                "Оффлайн-синхронизация: доменные области offline-first, meta-параметры, "
                "начальный снимок данных, получение изменений после последней синхронизации "
                "и batch-отправка оффлайн-операций с идемпотентностью по clientMutationId."
            ),
        },
        {
            "name": "finance-calendar",
            "description": (
                "Финансовый календарь: месячная сетка, события доходов и расходов, "
                "плановые операции, дневные балансы, прогноз остатка, риски "
                "кассового разрыва и справочники фильтров."
            ),
        },
        {
            "name": "pwa",
            "description": (
                "PWA-инфраструктура: регистрация push-подписок браузера, "
                "хранение ключей подписки, настройки push-уведомлений и "
                "параметры background sync для Service Worker."
            ),
        },
        {
            "name": "app-settings",
            "description": (
                "Настройки приложения текущего пользователя: часовой пояс, "
                "формат даты, формат чисел, валюта по умолчанию, справочники "
                "для формы и сброс к значениям по умолчанию."
            ),
        },
        {
            "name": "health",
            "description": "Служебные endpoints состояния backend-сервиса.",
        },
        {
            "name": "monitoring",
            "description": "Endpoints мониторинга и метрик backend-сервиса.",
        },
    ],
    "CONTACT": {
        "name": "BudgetWiseBackend",
        "email": "noreply@budgetwise.local",
    },
    "LICENSE": {
        "name": "Educational project",
    },
    "APPEND_COMPONENTS": {
        "schemas": {
            "ApiErrorDetail": {
                "type": "object",
                "description": "Детальная информация об ошибке API.",
                "properties": {
                    "status_code": {
                        "type": "integer",
                        "example": 400,
                    },
                    "code": {
                        "type": "string",
                        "example": "invalid",
                    },
                    "message": {
                        "type": "string",
                        "example": "Некорректные данные запроса.",
                    },
                    "field_errors": {
                        "type": "object",
                        "nullable": True,
                        "additionalProperties": True,
                        "example": {
                            "email": ["Введите корректный адрес электронной почты."]
                        },
                    },
                    "detail": {
                        "nullable": True,
                        "oneOf": [
                            {
                                "type": "string",
                            },
                            {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                            },
                        ],
                        "example": "Ошибка валидации.",
                    },
                    "trace_id": {
                        "type": "string",
                        "nullable": True,
                        "example": "test-trace-id-123",
                    },
                },
            },
            "ApiErrorResponse": {
                "type": "object",
                "description": "Единый формат ответа API при ошибке.",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "example": False,
                    },
                    "error": {
                        "$ref": "#/components/schemas/ApiErrorDetail",
                    },
                },
            },
        },
    },
}


ACCESS_TOKEN_LIFETIME_MINUTES = env.int(
    "ACCESS_TOKEN_LIFETIME_MINUTES",
    default=15,
)

REFRESH_TOKEN_LIFETIME_DAYS = env.int(
    "REFRESH_TOKEN_LIFETIME_DAYS",
    default=7,
)


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_LIFETIME_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS),
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