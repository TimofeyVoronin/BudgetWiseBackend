from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.app_settings.services import (
    build_app_settings_meta,
    get_or_create_user_app_settings,
    reset_user_app_settings,
)
from apps.users.app_settings.serializers import (
    AppSettingsMetaResponseSerializer,
    AppSettingsResetResponseSerializer,
    AppSettingsSerializer,
    AppSettingsValidationErrorSerializer,
)


class AppSettingsView(GenericAPIView):
    serializer_class = AppSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return get_or_create_user_app_settings(self.request.user)

    @extend_schema(
        tags=["app-settings"],
        operation_id="app_settings_retrieve",
        summary="Получить настройки приложения текущего пользователя",
        description=(
            "Возвращает пользовательские настройки приложения: часовой пояс, "
            "формат даты, формат чисел и валюту по умолчанию. Если настройки ещё "
            "не создавались, backend создаёт запись со значениями по умолчанию: "
            "Asia/Krasnoyarsk, DD.MM.YYYY, ru-RU и основная валюта пользователя."
        ),
        responses={200: AppSettingsSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "timezone": "Asia/Krasnoyarsk",
                    "dateFormat": "DD.MM.YYYY",
                    "numberFormat": "ru-RU",
                    "defaultCurrency": "RUB",
                    "createdAt": "2026-05-24T10:00:00+0700",
                    "updatedAt": "2026-05-24T10:00:00+0700",
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return Response(serializer.data)

    @extend_schema(
        tags=["app-settings"],
        operation_id="app_settings_update",
        summary="Полностью сохранить настройки приложения",
        description=(
            "Полностью обновляет настройки приложения текущего пользователя. "
            "Валюта по умолчанию должна быть добавлена в список валют пользователя. "
            "Машинные даты и суммы в API остаются стабильными, а эти настройки "
            "используются для display-полей и поведения интерфейса."
        ),
        request=AppSettingsSerializer,
        responses={200: AppSettingsSerializer, 400: AppSettingsValidationErrorSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "timezone": "Asia/Krasnoyarsk",
                    "dateFormat": "DD.MM.YYYY",
                    "numberFormat": "ru-RU",
                    "defaultCurrency": "RUB",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Ошибка валидации",
                value={
                    "success": False,
                    "error": {
                        "code": "invalid",
                        "message": "Некорректные данные запроса.",
                        "field_errors": {
                            "timezone": ["Выберите часовой пояс из списка доступных значений: Asia/Krasnoyarsk, Europe/Moscow, UTC."],
                            "defaultCurrency": ["Скрытую валюту нельзя выбрать как новую валюту по умолчанию."],
                        },
                        "status_code": 400,
                        "trace_id": None,
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def put(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            self.get_object(),
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        return Response(self.get_serializer(settings).data)

    @extend_schema(
        tags=["app-settings"],
        operation_id="app_settings_partial_update",
        summary="Частично сохранить настройки приложения",
        description=(
            "Частично обновляет настройки приложения текущего пользователя. "
            "Можно передать только изменившиеся поля."
        ),
        request=AppSettingsSerializer,
        responses={200: AppSettingsSerializer, 400: AppSettingsValidationErrorSerializer},
        examples=[
            OpenApiExample(
                "Пример запроса",
                value={
                    "timezone": "Europe/Moscow",
                    "numberFormat": "en-US",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Ошибка валидации",
                value={
                    "success": False,
                    "error": {
                        "code": "invalid",
                        "message": "Некорректные данные запроса.",
                        "field_errors": {
                            "dateFormat": ["Недопустимый формат даты. Доступны: DD.MM.YYYY, YYYY-MM-DD, MM/DD/YYYY."],
                        },
                        "status_code": 400,
                        "trace_id": None,
                    },
                },
                response_only=True,
                status_codes=["400"],
            ),
        ],
    )
    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            self.get_object(),
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        return Response(self.get_serializer(settings).data)


class AppSettingsMetaView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AppSettingsMetaResponseSerializer

    @extend_schema(
        tags=["app-settings"],
        operation_id="app_settings_meta_retrieve",
        summary="Получить справочники для страницы настроек приложения",
        description=(
            "Возвращает доступные часовые пояса, форматы даты, форматы чисел, "
            "валюты пользователя и значения по умолчанию для кнопки сброса."
        ),
        responses={200: AppSettingsMetaResponseSerializer},
    )
    def get(self, request, *args, **kwargs):
        return Response(build_app_settings_meta(request.user))


class AppSettingsResetView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AppSettingsResetResponseSerializer

    @extend_schema(
        tags=["app-settings"],
        operation_id="app_settings_reset",
        summary="Сбросить настройки приложения к значениям по умолчанию",
        description=(
            "Сбрасывает настройки текущего пользователя к значениям по умолчанию: "
            "Asia/Krasnoyarsk, DD.MM.YYYY, ru-RU и основная валюта пользователя."
        ),
        responses={200: AppSettingsResetResponseSerializer},
        examples=[
            OpenApiExample(
                "Успешный ответ",
                value={
                    "reset": True,
                    "settings": {
                        "timezone": "Asia/Krasnoyarsk",
                        "dateFormat": "DD.MM.YYYY",
                        "numberFormat": "ru-RU",
                        "defaultCurrency": "RUB",
                    },
                },
                response_only=True,
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        settings = reset_user_app_settings(request.user)
        return Response(
            {
                "reset": True,
                "settings": AppSettingsSerializer(
                    settings,
                    context={"request": request},
                ).data,
            }
        )
