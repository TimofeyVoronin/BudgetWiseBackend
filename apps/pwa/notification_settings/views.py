from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.pwa.notification_settings.serializers import PwaNotificationSettingsSerializer
from apps.pwa.notification_settings.services import get_or_create_pwa_notification_settings


class PwaNotificationSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_notification_settings_retrieve",
        summary="Получить настройки PWA-уведомлений",
        description=(
            "Возвращает настройки push-уведомлений текущего пользователя: включение канала, "
            "события синхронизации, бюджетные предупреждения, планируемые операции, "
            "импорт чеков и тихие часы."
        ),
        responses={200: PwaNotificationSettingsSerializer},
    )
    def get(self, request):
        settings = get_or_create_pwa_notification_settings(user=request.user)
        return Response(PwaNotificationSettingsSerializer(settings).data)

    @extend_schema(
        tags=["pwa"],
        operation_id="pwa_notification_settings_update",
        summary="Обновить настройки PWA-уведомлений",
        description="Полностью обновляет настройки push-уведомлений текущего пользователя.",
        request=PwaNotificationSettingsSerializer,
        responses={200: PwaNotificationSettingsSerializer},
        examples=[
            OpenApiExample(
                "Обновление настроек",
                value={
                    "pushEnabled": True,
                    "syncConflict": True,
                    "syncFailed": True,
                    "budgetLimitWarning": True,
                    "plannedTransactionDue": True,
                    "receiptImported": True,
                    "quietHoursEnabled": True,
                    "quietHoursFrom": "22:00",
                    "quietHoursTo": "08:00",
                },
                request_only=True,
            )
        ],
    )
    def put(self, request):
        settings = get_or_create_pwa_notification_settings(user=request.user)
        serializer = PwaNotificationSettingsSerializer(
            settings,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
