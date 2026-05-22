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
from apps.finance.currencies import (
    get_user_primary_currency_code,
    validate_user_currency_available,
)
from apps.finance.dashboard import (
    DASHBOARD_PERIOD_CUSTOM,
    DASHBOARD_PERIOD_TYPES,
    DEFAULT_DASHBOARD_PERIOD,
    DEFAULT_DASHBOARD_RECENT_LIMIT,
    MAX_DASHBOARD_RECENT_LIMIT,
    get_cached_dashboard_summary,
)
from apps.finance.dashboard_serializers import DashboardSummarySerializer
from apps.finance.tags import get_tag_ids_query_param


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
        return get_user_primary_currency_code(user)

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
                    "ISO-код добавленной валюты пользователя. Если параметр не передан, "
                    "используется основная валюта. Конвертация валют не выполняется, "
                    "данные фильтруются по валюте счёта."
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
