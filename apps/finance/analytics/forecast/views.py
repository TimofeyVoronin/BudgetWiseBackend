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

from apps.finance.analytics.combined.services import get_body_value
from apps.finance.analytics.forecast.exporters import (
    build_forecasting_export,
    normalize_export_format,
    normalize_export_sections,
)
from apps.finance.analytics.forecast.serializers import (
    ForecastingExportRequestSerializer,
    ForecastingMetaResponseSerializer,
    ForecastingProjectionResponseSerializer,
)
from apps.finance.analytics.forecast.services import (
    build_forecasting_filters_from_body,
    build_forecasting_filters_from_query,
    build_forecasting_meta,
    build_forecasting_projection,
)


FORECASTING_ANALYTICS_TAG = "finance-forecasting-analytics"


class ForecastingAnalyticsMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORECASTING_ANALYTICS_TAG],
        summary="Получить метаданные страницы прогнозирования",
        description=(
            "Возвращает опции фильтров и значения по умолчанию для страницы Forecasting: "
            "метрики, источники, горизонты, уровни доверия, модели и секции экспорта."
        ),
        responses={200: ForecastingMetaResponseSerializer},
    )
    def get(self, request):
        return Response(build_forecasting_meta(user=request.user))


class ForecastingAnalyticsProjectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORECASTING_ANALYTICS_TAG],
        summary="Получить прогноз финансовой метрики",
        description=(
            "Строит прогноз на основе завершённых месяцев истории. Поддерживает "
            "метрики income, expense, balance, источники all или id счёта, горизонты "
            "1/3/6/12/24 месяца, доверие 80/90/95/99 и модели linear/prophet. "
            "Prophet используется как опциональная модель с fallback на linear."
        ),
        parameters=[
            OpenApiParameter("metric", OpenApiTypes.STR, description="income, expense или balance."),
            OpenApiParameter("source", OpenApiTypes.STR, description="all или id счёта пользователя."),
            OpenApiParameter("horizon_months", OpenApiTypes.INT, description="1, 3, 6, 12 или 24."),
            OpenApiParameter("confidence", OpenApiTypes.INT, description="80, 90, 95 или 99."),
            OpenApiParameter("model", OpenApiTypes.STR, description="linear или prophet."),
        ],
        responses={
            200: ForecastingProjectionResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры прогноза."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Projection response",
                value={
                    "has_data": True,
                    "has_insufficient_data": False,
                    "has_high_instability": False,
                    "unstable": False,
                    "chart_points": [
                        {"month": "2026-05", "label": "Май 2026", "value": 135000, "is_forecast": False},
                        {
                            "month": "2026-06",
                            "label": "Июн 2026",
                            "value": 138000,
                            "lower_bound": 124000,
                            "upper_bound": 152000,
                            "is_forecast": True,
                        },
                    ],
                    "detail_rows": [
                        {"id": "2026-06", "month_label": "Июн 2026", "forecast_rub": 138000, "lower_rub": 124000, "upper_rub": 152000}
                    ],
                    "metric_summary": {
                        "total_forecast_rub": 873000,
                        "delta_percent": 8.7,
                        "delta_label": "к среднему за предыдущий период",
                        "positive_is_good": False,
                    },
                    "assumptions": {
                        "history_period_label": "Янв 2025 — Май 2026",
                        "source_label": "Все счета",
                        "model_label": "Линейная регрессия",
                        "updated_at_label": "27 мая 2026",
                    },
                    "alert": None,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        filters = build_forecasting_filters_from_query(
            user=request.user,
            query_params=request.query_params,
        )
        return Response(build_forecasting_projection(user=request.user, filters=filters))


class ForecastingAnalyticsExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FORECASTING_ANALYTICS_TAG],
        summary="Экспортировать отчёт прогнозирования",
        description=(
            "Формирует файл отчёта по тем же параметрам, что и endpoint projection. "
            "Поддерживает CSV, XLSX и PDF, а также секции history, forecast, confidence, parameters."
        ),
        request=ForecastingExportRequestSerializer,
        responses={
            200: OpenApiTypes.BINARY,
            400: OpenApiResponse(description="Некорректные параметры экспорта."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Export request",
                value={
                    "format": "pdf",
                    "sections": ["history", "forecast", "confidence", "parameters"],
                    "metric": "expense",
                    "source": "all",
                    "horizon_months": 6,
                    "confidence": 95,
                    "model": "linear",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        export_format = normalize_export_format(get_body_value(request.data, "format"))
        sections = normalize_export_sections(get_body_value(request.data, "sections"))
        filters = build_forecasting_filters_from_body(user=request.user, payload=request.data)
        projection = build_forecasting_projection(user=request.user, filters=filters)
        export_result = build_forecasting_export(
            projection=projection,
            export_format=export_format,
            sections=sections,
            metric=filters.metric,
        )
        response = HttpResponse(export_result.content, content_type=export_result.content_type)
        response["Content-Disposition"] = f'attachment; filename="{export_result.filename}"'
        return response
