from drf_spectacular.utils import (
    OpenApiExample,
    extend_schema,
    extend_schema_view,
)
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class APIRootResponseSerializer(serializers.Serializer):
    service = serializers.CharField()
    version = serializers.CharField()
    endpoints = serializers.DictField(child=serializers.CharField())


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
                        "settings": "/api/v1/settings/app/",
                        "finance": "/api/v1/finance/",
                        "pwa": "/api/v1/pwa/",
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
                    "settings": "/api/v1/settings/app/",
                    "finance": "/api/v1/finance/",
                    "pwa": "/api/v1/pwa/",
                    "schema": "/api/schema/",
                    "docs": "/api/docs/",
                    "redoc": "/api/redoc/",
                    "health": "/health/",
                    "metrics": "/metrics/",
                },
            }
        )
