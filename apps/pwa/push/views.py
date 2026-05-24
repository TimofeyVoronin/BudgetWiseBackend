from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pwa.push.serializers import (
    PWA_META_EXAMPLE,
    PwaMetaSerializer,
    PwaPushSubscriptionCreateSerializer,
    PwaPushSubscriptionDeleteSerializer,
    PwaPushSubscriptionSerializer,
    PwaPushSubscriptionsListSerializer,
    PwaPushSubscriptionTestResponseSerializer,
)
from apps.pwa.push.services import (
    build_push_test_result,
    build_pwa_meta,
    get_user_push_subscription,
    list_push_subscriptions,
    register_push_subscription,
    revoke_push_subscription,
)


class PwaMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_meta_retrieve",
        summary="Получить параметры PWA-возможностей",
        description=(
            "Возвращает параметры PWA-инфраструктуры: доступность push-подписок, "
            "фоновую синхронизацию, публичный VAPID-ключ и поддерживаемые события."
        ),
        responses={200: PwaMetaSerializer},
        examples=[PWA_META_EXAMPLE],
    )
    def get(self, request):
        return Response(build_pwa_meta())


class PwaPushSubscriptionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_push_subscriptions_list",
        summary="Получить push-подписки пользователя",
        description="Возвращает список сохранённых PWA push-подписок текущего пользователя.",
        responses={200: PwaPushSubscriptionsListSerializer},
    )
    def get(self, request):
        subscriptions = list_push_subscriptions(user=request.user)
        return Response(
            {
                "items": PwaPushSubscriptionSerializer(subscriptions, many=True).data,
            }
        )

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_push_subscription_create",
        summary="Зарегистрировать push-подписку",
        description=(
            "Создаёт или обновляет push-подписку браузера. Идемпотентность обеспечивается "
            "по паре текущий пользователь + endpoint. Ключи p256dh/auth сохраняются, но "
            "не возвращаются в ответе API."
        ),
        request=PwaPushSubscriptionCreateSerializer,
        responses={201: PwaPushSubscriptionSerializer},
        examples=[
            OpenApiExample(
                "Регистрация подписки",
                value={
                    "deviceId": "browser-device-id",
                    "endpoint": "https://push.example.test/subscription/abc",
                    "p256dh": "client-public-key",
                    "auth": "client-auth-secret",
                    "browser": "Chrome",
                    "platform": "Windows",
                    "userAgent": "Mozilla/5.0",
                    "isActive": True,
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = PwaPushSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subscription = register_push_subscription(
            user=request.user,
            data=serializer.validated_data,
        )

        return Response(
            PwaPushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )


class PwaPushSubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_push_subscription_delete",
        summary="Отключить push-подписку",
        description=(
            "Выполняет soft-delete push-подписки текущего пользователя: подписка остаётся "
            "в базе, но переводится в состояние isActive=false."
        ),
        parameters=[
            OpenApiParameter(
                "id",
                OpenApiTypes.INT,
                OpenApiParameter.PATH,
                description="ID push-подписки.",
            ),
        ],
        responses={200: PwaPushSubscriptionDeleteSerializer},
    )
    def delete(self, request, pk: int):
        subscription = revoke_push_subscription(
            user=request.user,
            subscription_id=pk,
        )
        return Response(
            {
                "deleted": True,
                "id": str(subscription.pk),
            }
        )


class PwaPushSubscriptionTestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_push_subscription_test_create",
        summary="Отправить тестовое push-уведомление",
        description=(
            "Проверяет сохранённую push-подписку. На этапе BUD-1133 endpoint возвращает "
            "контролируемый ответ о том, что реальный push-провайдер ещё не подключён."
        ),
        parameters=[
            OpenApiParameter(
                "id",
                OpenApiTypes.INT,
                OpenApiParameter.PATH,
                description="ID push-подписки.",
            ),
        ],
        request=None,
        responses={200: PwaPushSubscriptionTestResponseSerializer},
    )
    def post(self, request, pk: int):
        subscription = get_user_push_subscription(
            user=request.user,
            subscription_id=pk,
        )
        return Response(build_push_test_result(subscription=subscription))
