from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response


class HealthCheckResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
    version = serializers.CharField()
    timestamp = serializers.DateTimeField()


class APIRootResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    version = serializers.CharField()
    endpoints = serializers.DictField(child=serializers.CharField())


@extend_schema(
    tags=["health"],
    operation_id="health_check",
    summary="Проверка состояния backend-сервиса",
    responses={200: HealthCheckResponseSerializer},
    examples=[
        OpenApiExample(
            "Успешный ответ",
            value={
                "status": "ok",
                "service": "BudgetWiseBackend",
                "version": "1.0.0",
                "timestamp": "2026-05-09T00:00:00+00:00",
            },
            response_only=True,
        )
    ],
)
@api_view(["GET"])
def health_check(request):
    return Response(
        {
            "status": "ok",
            "service": "BudgetWiseBackend",
            "version": "1.0.0",
            "timestamp": timezone.now(),
        }
    )


@extend_schema_view(
    get=extend_schema(
        tags=["health"],
        operation_id="api_root",
        summary="Корневой endpoint API версии v1",
        responses={200: APIRootResponseSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "service": "BudgetWiseBackend API",
                    "version": "v1",
                    "endpoints": {
                        "users": "/api/v1/users/",
                        "finance": "/api/v1/finance/",
                        "schema": "/api/schema/",
                        "docs": "/api/docs/",
                        "health": "/health/",
                    },
                },
                response_only=True,
            )
        ],
    )
)
class APIRootView(GenericAPIView):
    serializer_class = APIRootResponseSerializer

    def get(self, request):
        return Response(
            {
                "service": "BudgetWiseBackend API",
                "version": "v1",
                "endpoints": {
                    "users": "/api/v1/users/",
                    "finance": "/api/v1/finance/",
                    "schema": "/api/schema/",
                    "docs": "/api/docs/",
                    "health": "/health/",
                },
            }
        )