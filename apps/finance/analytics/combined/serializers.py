from __future__ import annotations

from rest_framework import serializers


class CombinedAnalyticsSelectOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class CombinedAnalyticsFilterCategoryOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class CombinedAnalyticsFilterAccountOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class CombinedAnalyticsExportSectionOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()


class CombinedAnalyticsMetaResponseSerializer(serializers.Serializer):
    period_presets = CombinedAnalyticsSelectOptionSerializer(many=True)
    period_options = CombinedAnalyticsSelectOptionSerializer(many=True)
    account_options = CombinedAnalyticsSelectOptionSerializer(many=True)
    category_options = CombinedAnalyticsSelectOptionSerializer(many=True)
    type_options = CombinedAnalyticsSelectOptionSerializer(many=True)
    filter_categories = CombinedAnalyticsFilterCategoryOptionSerializer(many=True)
    filter_accounts = CombinedAnalyticsFilterAccountOptionSerializer(many=True)
    export_sections = CombinedAnalyticsExportSectionOptionSerializer(many=True)
    default_period_id = serializers.CharField()
    default_date_from = serializers.CharField()
    default_date_to = serializers.CharField()
    default_account_ids = serializers.ListField(child=serializers.CharField())
    default_category_ids = serializers.ListField(child=serializers.CharField())
    default_operation_type = serializers.CharField()


class CombinedAnalyticsPieSliceSerializer(serializers.Serializer):
    category_id = serializers.CharField()
    category_name = serializers.CharField()
    category_color = serializers.CharField()
    amount_rub = serializers.FloatField()
    percent = serializers.FloatField()


class CombinedAnalyticsBarGroupSerializer(serializers.Serializer):
    category_id = serializers.CharField()
    category_name = serializers.CharField()
    previous_period_amount_rub = serializers.FloatField()
    current_period_amount_rub = serializers.FloatField()


class CombinedAnalyticsBarLegendSerializer(serializers.Serializer):
    previous_period_label = serializers.CharField()
    current_period_label = serializers.CharField()


class CombinedAnalyticsLinePointSerializer(serializers.Serializer):
    month = serializers.CharField()
    label = serializers.CharField()
    income_rub = serializers.FloatField()
    expense_rub = serializers.FloatField()
    balance_rub = serializers.FloatField()


class CombinedAnalyticsAggregateRowSerializer(serializers.Serializer):
    category_id = serializers.CharField()
    category_name = serializers.CharField()
    amount_rub = serializers.FloatField()
    percent = serializers.FloatField()


class CombinedAnalyticsAggregatesResponseSerializer(serializers.Serializer):
    has_data = serializers.BooleanField()
    period_label = serializers.CharField()
    total_expense_rub = serializers.FloatField()
    total_income_rub = serializers.FloatField()
    pie_slices = CombinedAnalyticsPieSliceSerializer(many=True)
    bar_groups = CombinedAnalyticsBarGroupSerializer(many=True)
    bar_legend = CombinedAnalyticsBarLegendSerializer()
    line_points = CombinedAnalyticsLinePointSerializer(many=True)
    aggregate_rows = CombinedAnalyticsAggregateRowSerializer(many=True)


class CombinedAnalyticsExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["pdf", "csv", "xlsx"])
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=["pie", "bar", "line", "table"]),
        allow_empty=False,
    )
    period_preset = serializers.ChoiceField(
        choices=["week", "month", "quarter", "year", "custom"],
        required=False,
    )
    period_id = serializers.CharField(required=False, allow_blank=True)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    account_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    category_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    operation_type = serializers.ChoiceField(
        choices=["expense", "income", "transfer"],
        required=False,
    )
    currency = serializers.CharField(required=False, allow_blank=True)


class CombinedAnalyticsExportResponseSerializer(serializers.Serializer):
    download_url = serializers.CharField()
    file_name = serializers.CharField()
    format = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
