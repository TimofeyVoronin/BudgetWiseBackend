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
    code = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    symbol = serializers.SerializerMethodField()
    rateToPrimary = serializers.DecimalField(
        source="rate_to_primary",
        max_digits=20,
        decimal_places=8,
        coerce_to_string=False,
        read_only=True,
    )
    isPrimary = serializers.BooleanField(source="is_primary", read_only=True)
    isVisible = serializers.BooleanField(source="is_visible", read_only=True)
    isCustom = serializers.BooleanField(source="is_custom", read_only=True)
    operationsCount = serializers.SerializerMethodField()
    flagIcon = serializers.CharField(source="flag_icon", read_only=True)

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
    totalCount = serializers.IntegerField()
    primaryCode = serializers.CharField()
    hiddenCount = serializers.IntegerField()


class CurrenciesListResponseSerializer(serializers.Serializer):
    items = CurrencyListRowSerializer(many=True)
    summary = CurrenciesListSummarySerializer()


class CurrencySelectOptionSerializer(serializers.Serializer):
    title = serializers.CharField()
    value = serializers.CharField()
    symbol = serializers.CharField(required=False)
    isPrimary = serializers.BooleanField(required=False)


class CurrenciesSelectOptionsResponseSerializer(serializers.Serializer):
    primaryCode = serializers.CharField()
    options = CurrencySelectOptionSerializer(many=True)


class CurrencyCatalogItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    flagIcon = serializers.CharField()
    popular = serializers.BooleanField(required=False)


class CurrenciesCatalogResponseSerializer(serializers.Serializer):
    items = CurrencyCatalogItemSerializer(many=True)


class AddCurrencyFromCatalogSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3)

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
    code = serializers.CharField(max_length=3)
    name = serializers.CharField(max_length=100)
    symbol = serializers.CharField(max_length=12)
    isVisible = serializers.BooleanField(default=True, required=False)

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
    name = serializers.CharField(max_length=100, required=False)
    symbol = serializers.CharField(max_length=12, required=False)
    isVisible = serializers.BooleanField(required=False)

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
    isVisible = serializers.BooleanField()

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "is_visible" in mutable_data and "isVisible" not in mutable_data:
            mutable_data["isVisible"] = mutable_data["is_visible"]
        return super().to_internal_value(mutable_data)


class DeleteCurrencyResponseSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    id = serializers.IntegerField()


class DeleteCurrencyConflictResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    operationsCount = serializers.IntegerField(required=False)
    canHide = serializers.BooleanField(required=False)


class ValidateCustomCurrencySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=3)
    name = serializers.CharField(max_length=100)
    symbol = serializers.CharField(max_length=12)
    excludeId = serializers.IntegerField(required=False, allow_null=True)

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "exclude_id" in mutable_data and "excludeId" not in mutable_data:
            mutable_data["excludeId"] = mutable_data["exclude_id"]
        return super().to_internal_value(mutable_data)


class CurrencyFormValidationErrorsSerializer(serializers.Serializer):
    code = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    symbol = serializers.CharField(required=False)
    general = serializers.CharField(required=False)


class ValidateCustomCurrencyResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    fieldErrors = CurrencyFormValidationErrorsSerializer()


class CheckCurrencyCodeResponseSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    message = serializers.CharField(required=False)


def build_select_options_payload(user) -> dict:
    from apps.finance.currencies import (
        build_currency_select_options,
        get_user_primary_currency_code,
    )

    return {
        "primaryCode": get_user_primary_currency_code(user),
        "options": build_currency_select_options(user),
    }
