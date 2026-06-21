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

from apps.finance.analytics.comparative.exporters import build_comparative_analytics_export
from apps.finance.analytics.comparative.serializers import (
    ComparativeAnalyticsComparisonResponseSerializer,
    ComparativeAnalyticsExportRequestSerializer,
    ComparativeAnalyticsMetaResponseSerializer,
)
from apps.finance.analytics.comparative.services import (
    build_comparative_analytics_comparison_from_body,
    build_comparative_analytics_comparison_from_query,
    build_comparative_analytics_meta,
    get_body_value,
    normalize_export_format,
    normalize_export_sections,
)


COMPARATIVE_ANALYTICS_TAG = "finance-comparative-analytics"


class ComparativeAnalyticsMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMPARATIVE_ANALYTICS_TAG],
        summary="Получить метаданные страницы сравнительной аналитики",
        description=(
            "Возвращает типы сравнения, годы, показатели, доступные сущности "
            "для сравнения и значения фильтров по умолчанию."
        ),
        responses={200: ComparativeAnalyticsMetaResponseSerializer},
    )
    def get(self, request):
        return Response(build_comparative_analytics_meta(user=request.user))


class ComparativeAnalyticsComparisonView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMPARATIVE_ANALYTICS_TAG],
        summary="Получить сравнительные агрегаты",
        description=(
            "Возвращает данные для страницы Comparative Analytics: выбранные "
            "сущности в порядке drag-and-drop, grouped bar chart, line chart, "
            "карточки сводки, таблицу различий и сравнение по категориям."
        ),
        parameters=[
            OpenApiParameter("comparison_type", OpenApiTypes.STR, description="periods, categories или accounts."),
            OpenApiParameter("year", OpenApiTypes.STR, description="Год сравнения, например 2026."),
            OpenApiParameter("metric", OpenApiTypes.STR, description="income, expense или balance."),
            OpenApiParameter("entity_ids", OpenApiTypes.STR, many=True, description="ID сравниваемых сущностей. Порядок важен."),
            OpenApiParameter("convert_to_rub", OpenApiTypes.BOOL, description="Приводить суммы счетов в разных валютах к RUB."),
        ],
        responses={
            200: ComparativeAnalyticsComparisonResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры сравнения."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Comparison response",
                value={
                    "has_data": True,
                    "has_mixed_currencies": False,
                    "entities": [
                        {
                            "id": "2026-06",
                            "label": "Июнь 2026",
                            "subtitle": "Период",
                            "amount_rub": 100000,
                            "color": "#F97316",
                            "has_data": True,
                            "currency_code": "RUB",
                        }
                    ],
                    "bar_groups": [{"key": "income", "label": "Доходы", "values": [100000]}],
                    "bar_legend": [{"id": "2026-06", "label": "Июнь 2026", "color": "#F97316", "has_data": True}],
                    "summary_cards": [],
                    "line_points": [],
                    "category_rows": [],
                    "difference_rows": [],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        return Response(
            build_comparative_analytics_comparison_from_query(
                user=request.user,
                query_params=request.query_params,
            )
        )


class ComparativeAnalyticsExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[COMPARATIVE_ANALYTICS_TAG],
        summary="Экспортировать отчёт сравнительной аналитики",
        description=(
            "Формирует файл отчёта по тем же параметрам, что и endpoint comparison. "
            "Поддерживает CSV, XLSX и PDF, а также секции legend, differences и charts."
        ),
        request=ComparativeAnalyticsExportRequestSerializer,
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
                    "sections": ["legend", "differences", "charts"],
                    "comparison_type": "periods",
                    "year": "2026",
                    "metric": "income",
                    "entity_ids": ["2026-06", "2026-05", "2026-04"],
                    "convert_to_rub": True,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        export_format = normalize_export_format(get_body_value(request.data, "format"))
        sections = normalize_export_sections(get_body_value(request.data, "sections"))
        comparison = build_comparative_analytics_comparison_from_body(
            user=request.user,
            payload=request.data,
        )
        export_result = build_comparative_analytics_export(
            comparison=comparison,
            export_format=export_format,
            sections=sections,
        )
        response = HttpResponse(
            export_result.content,
            content_type=export_result.content_type,
        )
        response["Content-Disposition"] = f'attachment; filename="{export_result.filename}"'
        return response
