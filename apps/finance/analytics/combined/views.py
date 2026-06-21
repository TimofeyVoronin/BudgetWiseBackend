from __future__ import annotations

from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.analytics.combined.exporters import build_combined_analytics_export
from apps.finance.analytics.combined.serializers import (
    CombinedAnalyticsAggregatesResponseSerializer,
    CombinedAnalyticsExportRequestSerializer,
    CombinedAnalyticsMetaResponseSerializer,
)
from apps.finance.analytics.combined.services import (
    build_combined_analytics_aggregates_from_body,
    build_combined_analytics_aggregates_from_query,
    build_combined_analytics_meta,
    get_body_value,
    normalize_export_format,
    normalize_export_sections,
)


COMBINED_ANALYTICS_TAG = "finance-combined-analytics"


class CombinedAnalyticsMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMBINED_ANALYTICS_TAG],
        summary="Получить метаданные страницы комбинированной аналитики",
        description=(
            "Возвращает опции фильтров и значения по умолчанию для страницы "
            "визуализации: пресеты периода, счета, категории, типы операций "
            "и доступные секции экспорта."
        ),
        responses={200: CombinedAnalyticsMetaResponseSerializer},
        examples=[
            OpenApiExample(
                "Meta response",
                value={
                    "period_presets": [
                        {"value": "week", "label": "Неделя"},
                        {"value": "month", "label": "Месяц"},
                    ],
                    "period_options": [{"value": "2026-05", "label": "Май 2026"}],
                    "account_options": [{"value": "all", "label": "Все"}],
                    "category_options": [{"value": "all", "label": "Все"}],
                    "type_options": [{"value": "expense", "label": "Расходы"}],
                    "filter_categories": [],
                    "filter_accounts": [],
                    "export_sections": [
                        {"id": "pie", "label": "Включить круговую диаграмму", "icon": "mdi-chart-donut"},
                    ],
                    "default_period_id": "2026-05",
                    "default_date_from": "01.05.2026",
                    "default_date_to": "31.05.2026",
                    "default_account_ids": [],
                    "default_category_ids": [],
                    "default_operation_type": "expense",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        return Response(build_combined_analytics_meta(user=request.user))


class CombinedAnalyticsAggregatesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMBINED_ANALYTICS_TAG],
        summary="Получить агрегаты для pie, bar и line диаграмм",
        description=(
            "Единый endpoint страницы комбинированной аналитики. Возвращает "
            "данные для круговой диаграммы по категориям, столбчатого сравнения "
            "с предыдущим периодом, линейного графика трендов и таблицы агрегатов."
        ),
        parameters=[
            OpenApiParameter("period_preset", OpenApiTypes.STR, description="week, month, quarter, year или custom."),
            OpenApiParameter("period_id", OpenApiTypes.STR, description="ID периода: YYYY-MM, YYYY-Q1, YYYY, YYYY-W23."),
            OpenApiParameter("date_from", OpenApiTypes.DATE, description="Дата начала периода для custom или явного диапазона."),
            OpenApiParameter("date_to", OpenApiTypes.DATE, description="Дата окончания периода для custom или явного диапазона."),
            OpenApiParameter("account_ids", OpenApiTypes.INT, many=True, description="ID счетов. Можно передать несколько раз."),
            OpenApiParameter("category_ids", OpenApiTypes.INT, many=True, description="ID категорий. Можно передать несколько раз."),
            OpenApiParameter("operation_type", OpenApiTypes.STR, description="expense, income или transfer."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="ISO-код валюты отображения. По умолчанию RUB."),
        ],
        responses={
            200: CombinedAnalyticsAggregatesResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры фильтров."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Aggregates response",
                value={
                    "has_data": True,
                    "period_label": "Май 2026",
                    "total_expense_rub": 128450,
                    "total_income_rub": 100000,
                    "pie_slices": [
                        {
                            "category_id": "1",
                            "category_name": "Продукты",
                            "category_color": "#4f46e5",
                            "amount_rub": 41100,
                            "percent": 32,
                        }
                    ],
                    "bar_groups": [
                        {
                            "category_id": "1",
                            "category_name": "Продукты",
                            "previous_period_amount_rub": 42000,
                            "current_period_amount_rub": 41100,
                        }
                    ],
                    "bar_legend": {
                        "previous_period_label": "Апрель 2026",
                        "current_period_label": "Май 2026",
                    },
                    "line_points": [
                        {
                            "month": "2026-05",
                            "label": "Май 2026",
                            "income_rub": 100000,
                            "expense_rub": 128450,
                            "balance_rub": -28450,
                        }
                    ],
                    "aggregate_rows": [
                        {
                            "category_id": "1",
                            "category_name": "Продукты",
                            "amount_rub": 41100,
                            "percent": 32,
                        }
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        return Response(
            build_combined_analytics_aggregates_from_query(
                user=request.user,
                query_params=request.query_params,
            )
        )


class CombinedAnalyticsExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMBINED_ANALYTICS_TAG],
        summary="Экспортировать отчёт комбинированной аналитики",
        description=(
            "Формирует файл отчёта по тем же фильтрам, что и endpoint aggregates. "
            "Поддерживаются форматы CSV, XLSX и PDF, а также выбор секций: pie, bar, line, table."
        ),
        request=CombinedAnalyticsExportRequestSerializer,
        responses={
            200: OpenApiTypes.BINARY,
            400: OpenApiResponse(description="Некорректные параметры экспорта."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Export request",
                value={
                    "format": "xlsx",
                    "sections": ["pie", "bar", "line", "table"],
                    "period_preset": "month",
                    "period_id": "2026-05",
                    "account_ids": [1, 2],
                    "category_ids": [3, 4],
                    "operation_type": "expense",
                    "currency": "RUB",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        export_format = normalize_export_format(get_body_value(request.data, "format"))
        sections = normalize_export_sections(get_body_value(request.data, "sections"))
        aggregates = build_combined_analytics_aggregates_from_body(
            user=request.user,
            payload=request.data,
        )
        export_result = build_combined_analytics_export(
            aggregates=aggregates,
            export_format=export_format,
            sections=sections,
        )

        response = HttpResponse(
            export_result.content,
            content_type=export_result.content_type,
        )
        response["Content-Disposition"] = f'attachment; filename="{export_result.filename}"'
        return response
