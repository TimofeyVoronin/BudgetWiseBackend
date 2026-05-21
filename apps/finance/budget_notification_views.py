from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.budget_notification_serializers import (
    BudgetNotificationPreviewSerializer,
    BudgetNotificationsMetaSerializer,
    BudgetNotificationsSettingsResponseSerializer,
    SendBudgetNotificationTestResponseSerializer,
    SendBudgetNotificationTestSerializer,
    UpdateBudgetNotificationsSettingsSerializer,
    ValidateBudgetNotificationThresholdsResponseSerializer,
    ValidateBudgetNotificationThresholdsSerializer,
    get_current_budget_notifications_payload,
)


BUDGET_NOTIFICATION_SETTINGS_EXAMPLE = {
    "enabled": True,
    "thresholdsEnabled": True,
    "thresholds": [
        {
            "id": "near_limit",
            "label": "Приближение к лимиту",
            "hint": "Уведомление отправится один раз при пересечении порога.",
            "percent": 80,
            "active": True,
            "locked": False,
        },
        {
            "id": "warning",
            "label": "Предупреждение",
            "hint": "Уведомление отправится один раз при пересечении порога.",
            "percent": 90,
            "active": True,
            "locked": False,
        },
        {
            "id": "critical",
            "label": "Критический порог",
            "hint": "Фиксированный системный порог превышения бюджета.",
            "percent": 100,
            "active": False,
            "locked": True,
        },
    ],
    "events": [
        {
            "id": "budget_near_limit",
            "group": "budget",
            "label": "Бюджет: приближение к лимиту",
            "icon": "trending-up",
            "iconTone": "warning",
            "enabled": True,
        }
    ],
    "channels": [
        {
            "id": "in_app",
            "label": "In-app",
            "description": "Центр уведомлений в приложении",
            "icon": "bell",
            "enabled": True,
            "deliveryHint": "Всегда доступно",
            "deliveryOk": True,
            "deliveryStatus": "available",
        },
        {
            "id": "email",
            "label": "Электронная почта",
            "description": "Email пользователя",
            "icon": "mail",
            "enabled": False,
            "deliveryHint": "Канал будет подключен позже.",
            "deliveryOk": False,
            "deliveryStatus": "not_configured",
        },
    ],
    "antiSpam": {
        "minRepeatHours": 24,
        "groupNotifications": True,
        "cooldownMinutes": 15,
    },
    "goals": {
        "milestonePercents": [25, 50, 75, 100],
        "milestoneEnabled": {
            "25": True,
            "50": True,
            "75": True,
            "100": True,
        },
        "notifyOnLag": False,
        "lagDays": 7,
        "selectedGoalIds": [],
    },
    "previewUsagePercent": 87,
    "updatedAt": "2026-05-21T18:00:00+0300",
}


class BudgetNotificationSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Получить настройки уведомлений о бюджетах и целях",
        description=(
            "Возвращает настройки текущего пользователя для страницы уведомлений: "
            "включение уведомлений, пороги бюджета, типы событий, каналы доставки, "
            "защиту от дублей и настройки целей накопления. На текущем этапе "
            "реально доступен in-app канал, email и push сохраняются как будущие каналы."
        ),
        responses={200: BudgetNotificationsSettingsResponseSerializer},
        examples=[
            OpenApiExample(
                "Настройки уведомлений",
                value=BUDGET_NOTIFICATION_SETTINGS_EXAMPLE,
                response_only=True,
            )
        ],
    )
    def get(self, request):
        settings = get_current_budget_notifications_payload(user=request.user)
        serializer = BudgetNotificationsSettingsResponseSerializer(settings)
        return Response(serializer.data)

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Обновить настройки уведомлений о бюджетах и целях",
        description=(
            "Частично обновляет настройки уведомлений текущего пользователя. "
            "Можно передавать только изменённые секции: пороги, события, каналы, "
            "antiSpam или goals. Пороги валидируются: активные значения должны идти "
            "по возрастанию и не повторяться."
        ),
        request=UpdateBudgetNotificationsSettingsSerializer,
        responses={
            200: BudgetNotificationsSettingsResponseSerializer,
            400: OpenApiResponse(description="Ошибка валидации настроек."),
            409: OpenApiResponse(description="Настройки временно заблокированы cooldown-паузой."),
        },
        examples=[
            OpenApiExample(
                "Обновить пороги и каналы",
                value={
                    "enabled": True,
                    "thresholds": [
                        {
                            "id": "near_limit",
                            "percent": 80,
                            "active": True,
                        },
                        {
                            "id": "warning",
                            "percent": 90,
                            "active": True,
                        },
                    ],
                    "channels": [
                        {
                            "id": "in_app",
                            "enabled": True,
                        },
                        {
                            "id": "email",
                            "enabled": False,
                        },
                    ],
                },
                request_only=True,
            )
        ],
    )
    def patch(self, request):
        settings = get_current_budget_notifications_payload(user=request.user)
        serializer = UpdateBudgetNotificationsSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings = serializer.update_settings(settings=settings)
        return Response(BudgetNotificationsSettingsResponseSerializer(settings).data)

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Сохранить настройки уведомлений о бюджетах и целях",
        description="Полный или частичный вариант сохранения. Работает так же, как PATCH.",
        request=UpdateBudgetNotificationsSettingsSerializer,
        responses={200: BudgetNotificationsSettingsResponseSerializer, 400: OpenApiResponse(description="Ошибка валидации настроек.")},
    )
    def post(self, request):
        return self.patch(request)


class BudgetNotificationThresholdValidationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Проверить пороги бюджетных уведомлений",
        description=(
            "Проверяет пороги без сохранения настроек. Используется фронтом для "
            "валидации слайдеров: проценты должны быть в диапазоне 1..100, "
            "активные пороги должны идти по возрастанию и не повторяться."
        ),
        request=ValidateBudgetNotificationThresholdsSerializer,
        responses={200: ValidateBudgetNotificationThresholdsResponseSerializer, 400: OpenApiResponse(description="Невалидное тело запроса.")},
    )
    def post(self, request):
        serializer = ValidateBudgetNotificationThresholdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validate_thresholds_for_user(user=request.user))


class BudgetNotificationTestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Отправить тестовое уведомление",
        description=(
            "Возвращает результат тестовой доставки по выбранным каналам. "
            "На текущем этапе in-app канал считается доставленным, а email и push "
            "возвращаются как skipped, потому что реальные провайдеры не подключены."
        ),
        request=SendBudgetNotificationTestSerializer,
        responses={200: SendBudgetNotificationTestResponseSerializer, 400: OpenApiResponse(description="Ошибка валидации каналов или типа события.")},
        examples=[
            OpenApiExample(
                "Тест in-app уведомления",
                value={
                    "channelIds": ["in_app"],
                    "eventId": "budget_near_limit",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Результат теста",
                value={
                    "sent": True,
                    "channels": [
                        {
                            "id": "in_app",
                            "status": "delivered",
                        },
                        {
                            "id": "email",
                            "status": "skipped",
                            "error": "Канал доставки пока не настроен на backend.",
                        },
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        settings = get_current_budget_notifications_payload(user=request.user)
        serializer = SendBudgetNotificationTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.build_result(settings=settings))


class BudgetNotificationPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Получить предпросмотр уведомления",
        description=(
            "Возвращает пример текста уведомления для активных каналов доставки "
            "с учётом previewUsagePercent из пользовательских настроек."
        ),
        responses={200: BudgetNotificationPreviewSerializer},
    )
    def get(self, request):
        settings = get_current_budget_notifications_payload(user=request.user)
        return Response(BudgetNotificationPreviewSerializer.build_payload(settings=settings))


class BudgetNotificationMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["finance-budget-notifications"],
        summary="Получить справочники для настроек уведомлений",
        description=(
            "Возвращает цели накопления и справочные значения для выпадающих списков: "
            "интервалы повторов, cooldown, дни отставания и проценты рубежей целей."
        ),
        responses={200: BudgetNotificationsMetaSerializer},
    )
    def get(self, request):
        return Response(BudgetNotificationsMetaSerializer.build_payload(user=request.user))
