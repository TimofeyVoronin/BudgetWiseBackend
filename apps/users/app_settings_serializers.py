from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.users.app_settings import (
    build_app_settings_meta,
    get_allowed_timezone_values,
    is_valid_timezone,
    validate_default_currency_for_user,
)
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


class AppSettingsSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(
        max_length=64,
        help_text="Часовой пояс пользователя в формате IANA, например Asia/Krasnoyarsk.",
    )
    dateFormat = serializers.CharField(
        source="date_format",
        help_text="Формат отображения дат: DD.MM.YYYY, YYYY-MM-DD или MM/DD/YYYY.",
    )
    numberFormat = serializers.CharField(
        source="number_format",
        help_text="Формат отображения чисел: ru-RU или en-US.",
    )
    defaultCurrency = serializers.CharField(
        source="default_currency",
        max_length=3,
        help_text="Код валюты по умолчанию. Валюта должна быть добавлена пользователю.",
    )
    createdAt = serializers.DateTimeField(
        source="created_at",
        read_only=True,
        help_text="Дата создания настроек.",
    )
    updatedAt = serializers.DateTimeField(
        source="updated_at",
        read_only=True,
        help_text="Дата последнего обновления настроек.",
    )

    class Meta:
        model = UserAppSettings
        fields = [
            "timezone",
            "dateFormat",
            "numberFormat",
            "defaultCurrency",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["createdAt", "updatedAt"]

    def validate_timezone(self, value: str) -> str:
        value = str(value or "").strip()

        if not value:
            raise serializers.ValidationError("Часовой пояс обязателен.", code="required")

        if not is_valid_timezone(value):
            allowed = ", ".join(sorted(get_allowed_timezone_values()))
            raise serializers.ValidationError(
                f"Выберите часовой пояс из списка доступных значений: {allowed}.",
                code="invalid_timezone",
            )

        return value

    def validate_dateFormat(self, value: str) -> str:
        value = str(value or "").strip()

        if value not in AppDateFormat.values:
            raise serializers.ValidationError(
                "Недопустимый формат даты. Доступны: DD.MM.YYYY, YYYY-MM-DD, MM/DD/YYYY.",
                code="invalid_date_format",
            )

        return value

    def validate_numberFormat(self, value: str) -> str:
        value = str(value or "").strip()

        if value not in AppNumberFormat.values:
            raise serializers.ValidationError(
                "Недопустимый формат чисел. Доступны: ru-RU, en-US.",
                code="invalid_number_format",
            )

        return value

    def validate_defaultCurrency(self, value: str) -> str:
        request = self.context.get("request")
        if request is None:
            return str(value or "").strip().upper()

        current_value = None
        if self.instance is not None:
            current_value = getattr(self.instance, "default_currency", None)

        return validate_default_currency_for_user(
            request.user,
            value,
            current_value=current_value,
        )

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "date_format": "dateFormat",
            "number_format": "numberFormat",
            "default_currency": "defaultCurrency",
            "currency": "defaultCurrency",
        }
        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]
        return super().to_internal_value(mutable_data)


class AppSettingsResetResponseSerializer(serializers.Serializer):
    settings = AppSettingsSerializer(help_text="Настройки после сброса к значениям по умолчанию.")
    reset = serializers.BooleanField(help_text="Флаг успешного сброса.")


class AppSettingsTimezoneOptionSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="IANA timezone, например Asia/Krasnoyarsk.")
    label = serializers.CharField(help_text="Подпись для интерфейса.")
    offsetHours = serializers.IntegerField(help_text="Смещение от UTC в часах.")


class AppSettingsDateFormatOptionSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="Значение формата даты.")
    label = serializers.CharField(help_text="Подпись формата.")
    example = serializers.CharField(help_text="Пример отображения даты.")


class AppSettingsNumberFormatOptionSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="Значение формата чисел.")
    label = serializers.CharField(help_text="Подпись формата.")
    example = serializers.CharField(help_text="Пример отображения числа.")


class AppSettingsCurrencyOptionSerializer(serializers.Serializer):
    title = serializers.CharField(help_text="Подпись валюты для select-поля.")
    value = serializers.CharField(help_text="Код валюты.")
    symbol = serializers.CharField(required=False, help_text="Символ валюты.")
    isPrimary = serializers.BooleanField(required=False, help_text="Является ли валюта основной в управлении валютами.")
    isDefault = serializers.BooleanField(required=False, help_text="Выбрана ли валюта валютой по умолчанию в настройках приложения.")


class AppSettingsDefaultsSerializer(serializers.Serializer):
    timezone = serializers.CharField(help_text="Часовой пояс по умолчанию.")
    dateFormat = serializers.CharField(help_text="Формат даты по умолчанию.")
    numberFormat = serializers.CharField(help_text="Формат чисел по умолчанию.")
    defaultCurrency = serializers.CharField(help_text="Валюта по умолчанию.")


class AppSettingsMetaResponseSerializer(serializers.Serializer):
    timezones = AppSettingsTimezoneOptionSerializer(many=True, help_text="Доступные часовые пояса.")
    dateFormats = AppSettingsDateFormatOptionSerializer(many=True, help_text="Доступные форматы даты.")
    numberFormats = AppSettingsNumberFormatOptionSerializer(many=True, help_text="Доступные форматы чисел.")
    currencies = AppSettingsCurrencyOptionSerializer(many=True, help_text="Валюты пользователя для выбора валюты по умолчанию.")
    defaults = AppSettingsDefaultsSerializer(help_text="Значения по умолчанию для сброса настроек.")


class AppSettingsValidationErrorSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Код ошибки, например invalid.")
    message = serializers.CharField(help_text="Сообщение для пользователя.")
    fieldErrors = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text="Ошибки по полям формы.",
    )
