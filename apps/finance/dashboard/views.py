from datetime import date

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.validation import (
    get_date_query_param,
    get_int_query_param,
)
from apps.finance.currencies.services import (
    get_user_default_currency_code,
    validate_user_currency_available,
)
from apps.finance.dashboard.services import (
    DASHBOARD_PERIOD_CUSTOM,
    DASHBOARD_PERIOD_TYPES,
    DEFAULT_DASHBOARD_PERIOD,
    DEFAULT_DASHBOARD_RECENT_LIMIT,
    DASHBOARD_PERIOD_MONTH,
    DASHBOARD_WIDGET_PERIOD_TYPES,
    MAX_DASHBOARD_RECENT_LIMIT,
    build_dashboard_accounts_summary,
    build_dashboard_balance_summary,
    build_dashboard_expense_dynamics,
    build_dashboard_goals_summary,
    build_dashboard_period_currency_bar,
    get_cached_dashboard_summary,
)
from apps.finance.dashboard.serializers import (
    AccountsCardSerializer,
    BalanceCardSerializer,
    DashboardSummarySerializer,
    ExpenseDynamicsCardSerializer,
    GoalsCardSerializer,
    PeriodCurrencyBarSerializer,
)
from apps.finance.tags.services import get_tag_ids_query_param
from apps.users.app_settings.formatting import get_user_app_today


def get_dashboard_recent_limit(query_params) -> int:
    value = query_params.get("limit")

    if value in (None, ""):
        return DEFAULT_DASHBOARD_RECENT_LIMIT

    limit = get_int_query_param(query_params, "limit")

    if limit < 1 or limit > MAX_DASHBOARD_RECENT_LIMIT:
        raise ValidationError(
            {
                "limit": [
                    (
                        "Параметр limit должен быть от 1 до "
                        f"{MAX_DASHBOARD_RECENT_LIMIT}."
                    )
                ]
            }
        )

    return limit


def get_dashboard_period_query_param(query_params) -> str:
    period = query_params.get("period") or DEFAULT_DASHBOARD_PERIOD

    if period not in DASHBOARD_PERIOD_TYPES:
        raise ValidationError(
            {
                "period": [
                    "Параметр period должен быть week, month, year или custom."
                ]
            }
        )

    return period


def get_dashboard_currency_query_param(query_params, user) -> str:
    currency = query_params.get("currency")

    if currency in (None, ""):
        return get_user_default_currency_code(user)

    return validate_user_currency_available(
        user,
        currency,
        field_name="currency",
        require_visible=True,
    )


def get_dashboard_date_range_query_params(query_params, period: str):
    date_from = get_date_query_param(query_params, "date_from")
    date_to = get_date_query_param(query_params, "date_to")

    if period == DASHBOARD_PERIOD_CUSTOM and (date_from is None or date_to is None):
        raise ValidationError(
            {
                "date_from": [
                    "Для period=custom нужно указать date_from и date_to."
                ]
            }
        )

    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValidationError(
            {
                "date_from": [
                    "Параметр date_from не может быть позже date_to."
                ]
            }
        )

    return date_from, date_to


def get_dashboard_query_params(query_params, user) -> dict:
    period = get_dashboard_period_query_param(query_params)
    date_from, date_to = get_dashboard_date_range_query_params(
        query_params,
        period,
    )

    return {
        "period_type": period,
        "date_from": date_from,
        "date_to": date_to,
        "currency": get_dashboard_currency_query_param(query_params, user),
        "recent_limit": get_dashboard_recent_limit(query_params),
        "tag_ids": get_tag_ids_query_param(query_params, "tags", "tagIds", "tag_ids"),
    }


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        summary="Получить агрегированные данные главного дашборда",
        description=(
            "Возвращает основные агрегаты для главной страницы: общий баланс "
            "активных счетов, сумму доходов и расходов за текущий месяц, "
            "чистый результат, последние операции и топ категорий расходов. "
            "Блок reminders зарезервирован для будущего эпика напоминаний "
            "и пока возвращается с пустым списком rows. "
            "Можно ограничить расчёты конкретными тегами через tags/tagIds. "
            "Результат кэшируется на короткое время по пользователю, периоду, "
            "диапазону дат, валюте, limit и набору тегов."
        ),
        parameters=[
            OpenApiParameter(
                "period",
                OpenApiTypes.STR,
                description=(
                    "Период dashboard: week, month, year или custom. "
                    "По умолчанию month."
                ),
            ),
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description=(
                    "Дата начала периода. Обязательна для period=custom."
                ),
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description=(
                    "Дата окончания периода. Обязательна для period=custom."
                ),
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "ISO-код валюты отображения. Если параметр не передан, "
                    "используется валюта по умолчанию из настроек приложения. "
                    "Суммы пересчитываются backend-ом по актуальным курсам."
                ),
            ),
            OpenApiParameter(
                "limit",
                OpenApiTypes.INT,
                description=(
                    "Количество последних операций в блоке recent_transactions. "
                    f"По умолчанию {DEFAULT_DASHBOARD_RECENT_LIMIT}, "
                    f"максимум {MAX_DASHBOARD_RECENT_LIMIT}."
                ),
            ),
            OpenApiParameter(
                "tags",
                OpenApiTypes.STR,
                description=(
                    "ID тегов через запятую для фильтрации доходов, расходов, "
                    "последних операций и топа категорий. Например: tags=1,2."
                ),
            ),
            OpenApiParameter(
                "tagIds",
                OpenApiTypes.STR,
                description="Frontend-friendly alias для tags, например tagIds=1,2.",
            ),
        ],
        responses={200: DashboardSummarySerializer},
        examples=[
            OpenApiExample(
                "Dashboard summary",
                value={
                    "period": {
                        "type": "month",
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-17",
                    },
                    "currency": "RUB",
                    "totals": {
                        "accounts_balance": "13000.00",
                        "income": "50000.00",
                        "expense": "12450.00",
                        "net": "37550.00",
                    },
                    "recent_transactions": [
                        {
                            "id": 1,
                            "account": 1,
                            "account_name": "Основная карта",
                            "account_currency": "RUB",
                            "category": 2,
                            "category_name": "Продукты",
                            "category_icon": "shopping-cart",
                            "category_color": "#10B981",
                            "type": "expense",
                            "kind": "expense",
                            "amount": "1245.00",
                            "amount_abs": "1245.00",
                            "signed_amount": "-1245.00",
                            "description": "Покупка продуктов",
                            "operation_date": "2026-05-17",
                            "date": "2026-05-17",
                            "created_at": "2026-05-17T12:00:00+0300",
                            "updated_at": "2026-05-17T12:00:00+0300",
                            "tags": [
                                {
                                    "id": 1,
                                    "name": "Продукты",
                                    "groupId": 1,
                                    "groupName": "Покупки",
                                    "color": "#66BB6A",
                                    "icon": "cart",
                                    "isVisible": True,
                                }
                            ],
                        }
                    ],
                    "top_expense_categories": [
                        {
                            "category": 2,
                            "category_name": "Продукты",
                            "category_icon": "shopping-cart",
                            "category_color": "#10B981",
                            "total": "12450.00",
                        }
                    ],
                    "reminders": {
                        "title": "Напоминания",
                        "headerIcon": "bell",
                        "rows": [],
                        "footerLinkLabel": "Все напоминания",
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        query_params = get_dashboard_query_params(request.query_params, request.user)
        dashboard_data = get_cached_dashboard_summary(
            user=request.user,
            **query_params,
        )
        serializer = DashboardSummarySerializer(dashboard_data)

        return Response(serializer.data)


def get_dashboard_widget_period_query_param(query_params) -> str:
    period = query_params.get("period") or DEFAULT_DASHBOARD_PERIOD

    if period not in DASHBOARD_WIDGET_PERIOD_TYPES:
        raise ValidationError(
            {
                "period": [
                    "Параметр period должен быть week, month или year."
                ]
            }
        )

    return period


def get_dashboard_month_query_param(query_params, user) -> date:
    value = query_params.get("month")

    if value in (None, ""):
        today = get_user_app_today(user)
        return today.replace(day=1)

    normalized = str(value).strip()

    try:
        year_raw, month_raw = normalized.split("-", 1)
        year = int(year_raw)
        month = int(month_raw)
        return date(year, month, 1)
    except (TypeError, ValueError):
        raise ValidationError(
            {
                "month": [
                    "Параметр month должен быть в формате YYYY-MM, например 2026-05."
                ]
            }
        )


def get_dashboard_common_query_params(query_params, user) -> dict:
    period = get_dashboard_widget_period_query_param(query_params)
    return {
        "period_type": period,
        "currency": get_dashboard_currency_query_param(query_params, user),
    }


class DashboardPeriodCurrencyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        operation_id="finance_dashboard_period_currency_retrieve",
        summary="Получить настройки периода и валюты для dashboard",
        description=(
            "Возвращает модель верхней панели dashboard: период по умолчанию, "
            "валюту по умолчанию из настроек приложения и списки доступных периодов "
            "и видимых валют пользователя."
        ),
        responses={200: PeriodCurrencyBarSerializer},
        examples=[
            OpenApiExample(
                "Период и валюта dashboard",
                value={
                    "defaultPeriod": "month",
                    "defaultCurrency": "RUB",
                    "periodOptions": [
                        {"value": "week", "label": "Неделя"},
                        {"value": "month", "label": "Месяц"},
                        {"value": "year", "label": "Год"},
                    ],
                    "currencies": [
                        {"title": "Руб.", "value": "RUB"},
                        {"title": "Долл.", "value": "USD"},
                        {"title": "Евро", "value": "EUR"},
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        serializer = PeriodCurrencyBarSerializer(
            build_dashboard_period_currency_bar(user=request.user)
        )
        return Response(serializer.data)


class DashboardBalanceSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        operation_id="finance_dashboard_balance_summary_retrieve",
        summary="Получить карточку текущего баланса",
        description=(
            "Возвращает данные карточки текущего баланса для главной страницы. "
            "Параметр period задаёт период для расчёта тренда, currency задаёт "
            "валюту отображения. Счета и операции разных валют приводятся "
            "к выбранной валюте через единый сервис конвертации."
        ),
        parameters=[
            OpenApiParameter(
                "period",
                OpenApiTypes.STR,
                description="Период тренда: week, month или year. По умолчанию month.",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "ISO-код видимой валюты пользователя. Если не передан, "
                    "используется валюта по умолчанию из настроек приложения."
                ),
            ),
        ],
        responses={200: BalanceCardSerializer},
        examples=[
            OpenApiExample(
                "Карточка баланса",
                value={
                    "title": "Текущий баланс",
                    "headerIcon": "wallet",
                    "amountRub": 13000.0,
                    "trendLabel": "+12.5% к прошлому месяцу",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        query_params = get_dashboard_common_query_params(
            request.query_params,
            request.user,
        )
        serializer = BalanceCardSerializer(
            build_dashboard_balance_summary(
                user=request.user,
                **query_params,
            )
        )
        return Response(serializer.data)


class DashboardAccountsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        operation_id="finance_dashboard_accounts_summary_retrieve",
        summary="Получить карточку счетов",
        description=(
            "Возвращает превью активных неархивных счетов пользователя для dashboard. "
            "Параметр currency задаёт валюту отображения, балансы счетов "
            "пересчитываются в неё. Параметр period принимается для единого "
            "frontend-контракта, но на список счетов не влияет."
        ),
        parameters=[
            OpenApiParameter(
                "period",
                OpenApiTypes.STR,
                description="Период dashboard: week, month или year. По умолчанию month.",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "ISO-код видимой валюты пользователя. Если не передан, "
                    "используется валюта по умолчанию из настроек приложения."
                ),
            ),
        ],
        responses={200: AccountsCardSerializer},
        examples=[
            OpenApiExample(
                "Карточка счетов",
                value={
                    "title": "Счета",
                    "headerIcon": "credit-card",
                    "rows": [
                        {
                            "id": "1",
                            "name": "Основная карта",
                            "amountRub": 10000.0,
                            "icon": "card",
                        }
                    ],
                    "footerLinkLabel": "Все счета",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        query_params = get_dashboard_common_query_params(
            request.query_params,
            request.user,
        )
        serializer = AccountsCardSerializer(
            build_dashboard_accounts_summary(
                user=request.user,
                **query_params,
            )
        )
        return Response(serializer.data)


class DashboardGoalsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        operation_id="finance_dashboard_goals_summary_retrieve",
        summary="Получить карточку целей",
        description=(
            "Возвращает список активных целей для карточки на главной странице. "
            "Цели возвращаются в валюте отображения. Если цель привязана к счёту, "
            "её суммы пересчитываются из валюты счёта; цели без счёта "
            "считаются в основной валюте пользователя."
        ),
        parameters=[
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "ISO-код видимой валюты пользователя. Если не передан, "
                    "используется валюта по умолчанию из настроек приложения."
                ),
            ),
        ],
        responses={200: GoalsCardSerializer},
        examples=[
            OpenApiExample(
                "Карточка целей",
                value={
                    "title": "Цели",
                    "headerIcon": "target",
                    "goals": [
                        {
                            "id": "1",
                            "name": "Ремонт",
                            "targetRub": 500000.0,
                            "currentRub": 455000.0,
                            "percent": 91.0,
                        }
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        currency = get_dashboard_currency_query_param(request.query_params, request.user)
        serializer = GoalsCardSerializer(
            build_dashboard_goals_summary(
                user=request.user,
                currency=currency,
            )
        )
        return Response(serializer.data)


class DashboardExpenseDynamicsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-dashboard"],
        operation_id="finance_dashboard_expense_dynamics_retrieve",
        summary="Получить динамику расходов и доходов по неделям месяца",
        description=(
            "Возвращает модель столбчатого графика доходов и расходов. "
            "Месяц задаётся параметром month в формате YYYY-MM. Каждая точка weeks "
            "является неделей внутри выбранного месяца. Значения income и expenses "
            "нормализованы в диапазон 0-100 относительно максимального значения месяца."
        ),
        parameters=[
            OpenApiParameter(
                "month",
                OpenApiTypes.STR,
                description="Месяц графика в формате YYYY-MM, например 2026-05.",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description=(
                    "ISO-код видимой валюты пользователя. Если не передан, "
                    "используется валюта по умолчанию из настроек приложения."
                ),
            ),
        ],
        responses={200: ExpenseDynamicsCardSerializer},
        examples=[
            OpenApiExample(
                "Динамика по неделям",
                value={
                    "title": "Динамика расходов и доходов",
                    "headerIcon": "bar-chart-3",
                    "monthLabel": "Май",
                    "legendIncome": "Доходы",
                    "legendExpenses": "Расходы",
                    "yAxisLabels": ["0", "25", "50", "75", "100"],
                    "weeks": [
                        {"label": "1 неделя", "income": 100, "expenses": 40},
                        {"label": "2 неделя", "income": 0, "expenses": 25},
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        currency = get_dashboard_currency_query_param(request.query_params, request.user)
        month = get_dashboard_month_query_param(request.query_params, request.user)
        serializer = ExpenseDynamicsCardSerializer(
            build_dashboard_expense_dynamics(
                user=request.user,
                month=month,
                currency=currency,
            )
        )
        return Response(serializer.data)
