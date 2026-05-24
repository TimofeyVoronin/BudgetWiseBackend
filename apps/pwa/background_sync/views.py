from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pwa.background_sync.serializers import PwaBackgroundSyncMetaSerializer


class PwaBackgroundSyncMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_background_sync_meta_retrieve",
        summary="Получить параметры фоновой синхронизации PWA",
        description=(
            "Возвращает endpoints и параметры, которые Service Worker может использовать "
            "для background sync: push изменений, pull изменений, статус и журнал операций."
        ),
        responses={200: PwaBackgroundSyncMetaSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "enabled": True,
                    "syncEndpoint": "/api/v1/finance/sync/push/",
                    "pullEndpoint": "/api/v1/finance/sync/pull/",
                    "statusEndpoint": "/api/v1/finance/sync/status/",
                    "operationsEndpoint": "/api/v1/finance/sync/operations/",
                    "recommendedRetrySeconds": 30,
                    "maxBatchSize": 100,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        return Response(
            {
                "enabled": bool(getattr(settings, "PWA_BACKGROUND_SYNC_ENABLED", True)),
                "syncEndpoint": "/api/v1/finance/sync/push/",
                "pullEndpoint": "/api/v1/finance/sync/pull/",
                "statusEndpoint": "/api/v1/finance/sync/status/",
                "operationsEndpoint": "/api/v1/finance/sync/operations/",
                "recommendedRetrySeconds": int(
                    getattr(settings, "PWA_BACKGROUND_SYNC_RETRY_SECONDS", 30)
                ),
                "maxBatchSize": int(
                    getattr(settings, "OFFLINE_SYNC_MAX_BATCH_SIZE", 100)
                ),
            }
        )
