import hmac

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny


@extend_schema(
    tags=["monitoring"],
    operation_id="metrics",
    summary="Получить Prometheus-метрики backend-сервиса",
    description=(
        "Возвращает метрики backend API в Prometheus text format. "
        "Endpoint защищён заголовком X-Metrics-Token. "
        "Значение токена задаётся через переменную окружения METRICS_ACCESS_TOKEN."
    ),
    auth=[],
    parameters=[
        OpenApiParameter(
            name="X-Metrics-Token",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.HEADER,
            required=True,
            description="Token for accessing metrics endpoint.",
        )
    ],
    responses={
        200: OpenApiTypes.STR,
        403: OpenApiTypes.OBJECT,
    },
    examples=[
        OpenApiExample(
            "Фрагмент успешного ответа",
            value=(
                "# HELP django_http_requests_total_by_method_total "
                "Count of requests by method.\n"
                "# TYPE django_http_requests_total_by_method_total counter\n"
            ),
            response_only=True,
        )
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def metrics_view(request):
    expected_token = getattr(settings, "METRICS_ACCESS_TOKEN", "")
    provided_token = request.headers.get("X-Metrics-Token", "")

    if not expected_token or not hmac.compare_digest(
        provided_token,
        expected_token,
    ):
        raise PermissionDenied("Metrics endpoint access denied.")

    return HttpResponse(
        generate_latest(),
        content_type=CONTENT_TYPE_LATEST,
    )
