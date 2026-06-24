from __future__ import annotations

from rest_framework import serializers

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_PERIODS,
)


class FinancialHealthSummaryQuerySerializer(serializers.Serializer):
    period = serializers.CharField(required=False, allow_blank=True)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    currency = serializers.CharField(required=False, allow_blank=True, max_length=3)

    def validate_period(self, value: str) -> str:
        period = str(value or "").strip()
        if not period:
            return period
        if period not in FINANCIAL_HEALTH_PERIODS:
            raise serializers.ValidationError(
                "Недопустимый период расчёта. Поддерживаются: month, quarter, year, custom."
            )
        return period

    def validate_currency(self, value: str) -> str:
        currency = str(value or "").strip().upper()
        if not currency:
            return currency
        if len(currency) != 3 or not currency.isalpha():
            raise serializers.ValidationError(
                "Валюта должна быть указана ISO-кодом из 3 латинских букв."
            )
        return currency


class FinancialHealthScoreRangeSerializer(serializers.Serializer):
    min = serializers.IntegerField()
    max = serializers.IntegerField()


class FinancialHealthPeriodDefinitionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    requiresCustomDates = serializers.BooleanField()


class FinancialHealthLevelDefinitionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    minScore = serializers.IntegerField()
    maxScore = serializers.IntegerField()
    description = serializers.CharField()


class FinancialHealthMetricDefinitionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    weight = serializers.IntegerField()
    unit = serializers.CharField()
    higherIsBetter = serializers.BooleanField()
    source = serializers.CharField()


class FinancialHealthRecommendationPrioritySerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()


class FinancialHealthMetaResponseSerializer(serializers.Serializer):
    scoreRange = FinancialHealthScoreRangeSerializer()
    defaultPeriod = serializers.CharField()
    defaultCurrency = serializers.CharField()
    periods = FinancialHealthPeriodDefinitionSerializer(many=True)
    levels = FinancialHealthLevelDefinitionSerializer(many=True)
    metrics = FinancialHealthMetricDefinitionSerializer(many=True)
    recommendationPriorities = FinancialHealthRecommendationPrioritySerializer(many=True)
    summaryContract = serializers.DictField()


class FinancialHealthMoneyAmountSerializer(serializers.Serializer):
    amount = serializers.FloatField()
    currency = serializers.CharField()


class FinancialHealthPeriodSerializer(serializers.Serializer):
    type = serializers.CharField()
    dateFrom = serializers.CharField()
    dateTo = serializers.CharField()
    label = serializers.CharField()
    days = serializers.IntegerField(required=False)


class FinancialHealthTotalsSerializer(serializers.Serializer):
    income = FinancialHealthMoneyAmountSerializer()
    expenses = FinancialHealthMoneyAmountSerializer()
    netBalance = FinancialHealthMoneyAmountSerializer()
    accountsBalance = FinancialHealthMoneyAmountSerializer()
    availableBalance = FinancialHealthMoneyAmountSerializer()


class FinancialHealthMetricSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    weight = serializers.IntegerField()
    unit = serializers.CharField()
    higherIsBetter = serializers.BooleanField()
    value = serializers.FloatField(allow_null=True)
    score = serializers.IntegerField(min_value=0, max_value=100)
    level = serializers.CharField()
    details = serializers.DictField()


class FinancialHealthRecommendationSerializer(serializers.Serializer):
    code = serializers.CharField()
    priority = serializers.CharField()
    metricId = serializers.CharField()
    title = serializers.CharField()
    text = serializers.CharField()
    action = serializers.CharField()
    reason = serializers.CharField()


class FinancialHealthDataQualitySerializer(serializers.Serializer):
    hasEnoughData = serializers.BooleanField()
    transactionCount = serializers.IntegerField()
    accountCount = serializers.IntegerField()
    budgetCount = serializers.IntegerField()
    goalCount = serializers.IntegerField()
    plannedTransactionCount = serializers.IntegerField()
    periodDays = serializers.IntegerField()
    warnings = serializers.ListField(child=serializers.CharField())


class FinancialHealthSummaryResponseSerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    level = serializers.CharField()
    period = FinancialHealthPeriodSerializer()
    currency = serializers.CharField()
    totals = FinancialHealthTotalsSerializer()
    metrics = FinancialHealthMetricSerializer(many=True)
    recommendations = FinancialHealthRecommendationSerializer(many=True)
    dataQuality = FinancialHealthDataQualitySerializer()
