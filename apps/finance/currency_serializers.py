from __future__ import annotations

from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.finance.currencies import (
    CURRENCY_CATALOG,
    build_catalog_items,
    get_currency_usage_count,
    normalize_currency_code,
    normalize_currency_symbol,
    normalize_currency_text,
    validate_custom_currency_payload,
)
from apps.finance.models import UserCurrency


class CurrencyListRowSerializer(serializers.ModelSerializer):
    code = serializers.SerializerMethodField(help_text="Код валюты, например RUB, USD или BTC.")
    name = serializers.SerializerMethodField(help_text="Пользовательское или системное название валюты.")
    symbol = serializers.SerializerMethodField(help_text="Символ валюты, который показывается в интерфейсе.")
    rateToPrimary = serializers.DecimalField(
        source="rate_to_primary",
        max_digits=20,
        decimal_places=8,
        coerce_to_string=False,
        read_only=True,
        help_text="Курс к основной валюте пользователя. Для основной валюты всегда 1.0.",
    )
    isPrimary = serializers.BooleanField(source="is_primary", read_only=True, help_text="Является ли валюта основной.")
    isVisible = serializers.BooleanField(source="is_visible", read_only=True, help_text="Показывается ли валюта в интерфейсе и формах.")
    isCustom = serializers.BooleanField(source="is_custom", read_only=True, help_text="Является ли валюта пользовательской.")
    operationsCount = serializers.SerializerMethodField(help_text="Количество связанных объектов пользователя с этой валютой.")
    flagIcon = serializers.CharField(source="flag_icon", read_only=True, help_text="Код иконки валюты для интерфейса.")

    class Meta:
        model = UserCurrency
        fields = [
            "id",
            "code",
            "name",
            "symbol",
            "rateToPrimary",
            "isPrimary",
            "isVisible",
            "isCustom",
            "operationsCount",
            "flagIcon",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_code(self, obj: UserCurrency) -> str:
        return obj.code

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj: UserCurrency) -> str:
        return obj.display_name

    @extend_schema_field(OpenApiTypes.STR)
    def get_symbol(self, obj: UserCurrency) -> str:
        return obj.display_symbol

    @extend_schema_field(OpenApiTypes.INT)
    def get_operationsCount(self, obj: UserCurrency) -> int:
        return get_currency_usage_count(obj.user, obj.code)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["id"] = instance.pk
        if instance.is_primary:
            data["rateToPrimary"] = 1.0
        return data


class CurrenciesListSummarySerializer(serializers.Serializer):
    totalCount = serializers.IntegerField(help_text="Общее количество валют пользователя.")
    primaryCode = serializers.CharField(help_text="Код основной валюты пользователя.")
    hiddenCount = serializers.IntegerField(help_text="Количество скрытых валют.")


class CurrenciesListResponseSerializer(serializers.Serializer):
    items = CurrencyListRowSerializer(many=True, help_text="Список валют пользователя.")
    summary = CurrenciesListSummarySerializer(help_text="Сводка для страницы управления валютами.")


class CurrencySelectOptionSerializer(serializers.Serializer):
    title = serializers.CharField(help_text="Подпись валюты для select-поля.")
    value = serializers.CharField(help_text="Код валюты.")
    symbol = serializers.CharField(required=False, help_text="Символ валюты.")
    isPrimary = serializers.BooleanField(required=False, help_text="Является ли валюта основной.")


class CurrenciesSelectOptionsResponseSerializer(serializers.Serializer):
    primaryCode = serializers.CharField(help_text="Код основной валюты пользователя.")
    options = CurrencySelectOptionSerializer(many=True, help_text="Видимые валюты для форм.")


class CurrencyCatalogItemSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Код валюты из каталога.")
    name = serializers.CharField(help_text="Название валюты из каталога.")
    symbol = serializers.CharField(help_text="Символ валюты.")
    flagIcon = serializers.CharField(help_text="Код иконки валюты.")
    popular = serializers.BooleanField(required=False, help_text="Популярная валюта для быстрого выбора.")


class CurrenciesCatalogResponseSerializer(serializers.Serializer):
    items = CurrencyCatalogItemSerializer(many=True, help_text="Список валют из статического каталога.")


class AddCurrencyFromCatalogSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3, help_text="Код валюты из каталога, например USD.")

    def validate_code(self, value: str) -> str:
        normalized = normalize_currency_code(value)
        available_codes = {item["code"] for item in CURRENCY_CATALOG}

        if normalized not in available_codes:
            raise serializers.ValidationError(
                "Валюта не найдена в каталоге.",
                code="currency_catalog_not_found",
            )

        return normalized


class CreateCustomCurrencySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3, help_text="Код пользовательской валюты из 3 латинских букв.")
    name = serializers.CharField(max_length=100, help_text="Название пользовательской валюты.")
    symbol = serializers.CharField(max_length=12, help_text="Символ пользовательской валюты.")
    isVisible = serializers.BooleanField(default=True, required=False, help_text="Показывать валюту в интерфейсе.")

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "is_visible": "isVisible",
        }
        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    def validate(self, attrs):
        request = self.context.get("request")
        validation = validate_custom_currency_payload(
            code=attrs.get("code"),
            name=attrs.get("name"),
            symbol=attrs.get("symbol"),
            user=request.user if request else None,
        )

        if validation["fieldErrors"]:
            raise serializers.ValidationError(validation["fieldErrors"])

        attrs["code"] = validation["code"]
        attrs["name"] = validation["name"]
        attrs["symbol"] = validation["symbol"]
        return attrs


class UpdateCurrencySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False, help_text="Новое название пользовательской валюты.")
    symbol = serializers.CharField(max_length=12, required=False, help_text="Новый символ пользовательской валюты.")
    isVisible = serializers.BooleanField(required=False, help_text="Показывать валюту в интерфейсе.")

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "is_visible" in mutable_data and "isVisible" not in mutable_data:
            mutable_data["isVisible"] = mutable_data["is_visible"]
        return super().to_internal_value(mutable_data)

    def validate_name(self, value: str) -> str:
        normalized = normalize_currency_text(value)
        if not normalized:
            raise serializers.ValidationError(
                "Название валюты не может быть пустым.",
                code="currency_name_blank",
            )
        return normalized

    def validate_symbol(self, value: str) -> str:
        normalized = normalize_currency_symbol(value)
        if not normalized:
            raise serializers.ValidationError(
                "Символ валюты не может быть пустым.",
                code="currency_symbol_blank",
            )
        return normalized


class SetCurrencyVisibilitySerializer(serializers.Serializer):
    isVisible = serializers.BooleanField(help_text="Показывать валюту в интерфейсе и формах.")

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "is_visible" in mutable_data and "isVisible" not in mutable_data:
            mutable_data["isVisible"] = mutable_data["is_visible"]
        return super().to_internal_value(mutable_data)


class DeleteCurrencyResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField(help_text="Признак успешного удаления.")
    id = serializers.IntegerField(help_text="ID удалённой валюты пользователя.")


class DeleteCurrencyConflictResponseSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Код конфликта удаления.")
    message = serializers.CharField(help_text="Пояснение для пользователя.")
    operationsCount = serializers.IntegerField(required=False, help_text="Количество связанных объектов с этой валютой.")
    canHide = serializers.BooleanField(required=False, help_text="Можно ли скрыть валюту вместо удаления.")


class ValidateCustomCurrencySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3, required=False, allow_blank=True, help_text="Код проверяемой валюты.")
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, help_text="Название проверяемой валюты.")
    symbol = serializers.CharField(max_length=12, required=False, allow_blank=True, help_text="Символ проверяемой валюты.")
    excludeId = serializers.IntegerField(required=False, allow_null=True, help_text="ID валюты, которую нужно исключить при проверке дубля.")

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "exclude_id" in mutable_data and "excludeId" not in mutable_data:
            mutable_data["excludeId"] = mutable_data["exclude_id"]
        return super().to_internal_value(mutable_data)


class CurrencyFormValidationErrorsSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, help_text="Ошибка поля code.")
    name = serializers.CharField(required=False, help_text="Ошибка поля name.")
    symbol = serializers.CharField(required=False, help_text="Ошибка поля symbol.")
    general = serializers.CharField(required=False, help_text="Общая ошибка формы.")


class ValidateCustomCurrencyResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField(help_text="Форма прошла проверку.")
    fieldErrors = CurrencyFormValidationErrorsSerializer(help_text="Ошибки по полям формы.")


class CheckCurrencyCodeResponseSerializer(serializers.Serializer):
    available = serializers.BooleanField(help_text="Можно ли использовать код валюты.")
    message = serializers.CharField(required=False, help_text="Пояснение, если код недоступен.")


def build_select_options_payload(user) -> dict:
    from apps.finance.currencies import (
        build_currency_select_options,
        get_user_primary_currency_code,
    )

    return {
        "primaryCode": get_user_primary_currency_code(user),
        "options": build_currency_select_options(user),
    }
