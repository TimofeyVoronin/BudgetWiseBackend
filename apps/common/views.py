import hmac

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.common.health import build_health_status


class HealthCheckResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
    version = serializers.CharField()
    timestamp = serializers.DateTimeField()
    checks = serializers.DictField(child=serializers.JSONField())


class APIRootResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    version = serializers.CharField()
    endpoints = serializers.DictField(child=serializers.CharField())


@extend_schema(
    tags=["health"],
    operation_id="health_check",
    summary="Проверка состояния backend-сервиса и зависимостей",
    description=(
        "Возвращает состояние backend-сервиса и базовых зависимостей. "
        "Endpoint доступен без авторизации и может использоваться для "
        "health-check в Docker Compose, мониторинге и внешних проверках."
    ),
    auth=[],
    responses={
        200: HealthCheckResponseSerializer,
        503: HealthCheckResponseSerializer,
    },
    examples=[
        OpenApiExample(
            "Успешный ответ",
            value={
                "status": "ok",
                "service": "BudgetWiseBackend",
                "version": "1.0.0",
                "timestamp": "2026-05-10T00:00:00Z",
                "checks": {
                    "database": {
                        "status": "ok",
                        "required": True,
                        "latency_ms": 2.15,
                        "details": {
                            "alias": "default",
                            "vendor": "postgresql",
                        },
                    },
                    "redis": {
                        "status": "skipped",
                        "required": False,
                        "latency_ms": None,
                        "details": {
                            "reason": "Redis is not configured yet.",
                        },
                    },
                    "celery": {
                        "status": "skipped",
                        "required": False,
                        "latency_ms": None,
                        "details": {
                            "reason": "Celery health-check is not configured yet.",
                        },
                    },
                    "external_services": {
                        "status": "skipped",
                        "required": False,
                        "latency_ms": None,
                        "details": {
                            "reason": "External services are not configured yet.",
                        },
                    },
                },
            },
            response_only=True,
        )
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    health_data, http_status = build_health_status()

    response_data = {
        "status": health_data["status"],
        "service": "BudgetWiseBackend",
        "version": "1.0.0",
        "timestamp": timezone.now(),
        "checks": health_data["checks"],
    }

    return Response(
        response_data,
        status=(
            status.HTTP_200_OK
            if http_status == 200
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
    )


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


@extend_schema_view(
    get=extend_schema(
        tags=["health"],
        operation_id="api_root",
        summary="Корневой endpoint API версии v1",
        description=(
            "Возвращает основные группы endpoints backend API и ссылки "
            "на OpenAPI-документацию."
        ),
        auth=[],
        responses={200: APIRootResponseSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "service": "BudgetWiseBackend API",
                    "version": "v1",
                    "endpoints": {
                        "auth": "/api/v1/auth/",
                        "users": "/api/v1/users/",
                        "finance": "/api/v1/finance/",
                        "schema": "/api/schema/",
                        "docs": "/api/docs/",
                        "redoc": "/api/redoc/",
                        "health": "/health/",
                        "metrics": "/metrics/",
                    },
                },
                response_only=True,
            )
        ],
    )
)
class APIRootView(GenericAPIView):
    serializer_class = APIRootResponseSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "service": "BudgetWiseBackend API",
                "version": "v1",
                "endpoints": {
                    "auth": "/api/v1/auth/",
                    "users": "/api/v1/users/",
                    "finance": "/api/v1/finance/",
                    "schema": "/api/schema/",
                    "docs": "/api/docs/",
                    "redoc": "/api/redoc/",
                    "health": "/health/",
                    "metrics": "/metrics/",
                },
            }
        )