from __future__ import annotations

from rest_framework import serializers


class ComparativeAnalyticsSelectOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ComparativeAnalyticsExportSectionOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()


class ComparativeAnalyticsEntitySerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    subtitle = serializers.CharField()
    amount_rub = serializers.FloatField()
    color = serializers.CharField()
    has_data = serializers.BooleanField()
    currency_code = serializers.CharField()


class ComparativeAnalyticsMetaResponseSerializer(serializers.Serializer):
    max_entities = serializers.IntegerField()
    comparison_type_options = ComparativeAnalyticsSelectOptionSerializer(many=True)
    year_options = ComparativeAnalyticsSelectOptionSerializer(many=True)
    metric_options = ComparativeAnalyticsSelectOptionSerializer(many=True)
    report_period_options = ComparativeAnalyticsSelectOptionSerializer(many=True)
    export_sections = ComparativeAnalyticsExportSectionOptionSerializer(many=True)
    available_entities = serializers.DictField(
        child=ComparativeAnalyticsEntitySerializer(many=True),
    )
    default_comparison_type = serializers.CharField()
    default_year = serializers.CharField()
    default_metric = serializers.CharField()
    default_entity_ids = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
    )
    default_export_sections = serializers.ListField(child=serializers.CharField())
    default_report_period_id = serializers.CharField()


class ComparativeAnalyticsBarGroupSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    values = serializers.ListField(child=serializers.FloatField())


class ComparativeAnalyticsBarLegendItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    color = serializers.CharField()
    has_data = serializers.BooleanField()


class ComparativeAnalyticsSummaryCardSerializer(serializers.Serializer):
    label = serializers.CharField()
    amount_rub = serializers.FloatField()
    delta_percent = serializers.FloatField()
    delta_label = serializers.CharField()
    positive_is_good = serializers.BooleanField()


class ComparativeAnalyticsLinePointSerializer(serializers.Serializer):
    month = serializers.CharField()
    label = serializers.CharField()
    income_rub = serializers.FloatField()
    expense_rub = serializers.FloatField()


class ComparativeAnalyticsCategoryRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    previous_amount_rub = serializers.FloatField()
    current_amount_rub = serializers.FloatField()
    delta_percent = serializers.FloatField()


class ComparativeAnalyticsDifferenceRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    metric = serializers.CharField()
    value_a = serializers.FloatField()
    value_b = serializers.FloatField()
    delta_rub = serializers.FloatField()
    delta_percent = serializers.FloatField()
    positive_is_good = serializers.BooleanField()
    label_a = serializers.CharField(required=False, allow_blank=True)
    label_b = serializers.CharField(required=False, allow_blank=True)


class ComparativeAnalyticsComparisonResponseSerializer(serializers.Serializer):
    has_data = serializers.BooleanField()
    has_mixed_currencies = serializers.BooleanField()
    entities = ComparativeAnalyticsEntitySerializer(many=True)
    bar_groups = ComparativeAnalyticsBarGroupSerializer(many=True)
    bar_legend = ComparativeAnalyticsBarLegendItemSerializer(many=True)
    summary_cards = ComparativeAnalyticsSummaryCardSerializer(many=True)
    line_points = ComparativeAnalyticsLinePointSerializer(many=True)
    category_rows = ComparativeAnalyticsCategoryRowSerializer(many=True)
    difference_rows = ComparativeAnalyticsDifferenceRowSerializer(many=True)


class ComparativeAnalyticsExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["pdf", "csv", "xlsx"])
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=["legend", "differences", "charts"]),
        allow_empty=False,
    )
    comparison_type = serializers.ChoiceField(
        choices=["periods", "categories", "accounts"],
        required=False,
    )
    year = serializers.CharField(required=False, allow_blank=True)
    metric = serializers.ChoiceField(
        choices=["income", "expense", "balance"],
        required=False,
    )
    entity_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
    )
    report_period_id = serializers.CharField(required=False, allow_blank=True)
    convert_to_rub = serializers.BooleanField(required=False)


class ComparativeAnalyticsExportResponseSerializer(serializers.Serializer):
    download_url = serializers.CharField()
    file_name = serializers.CharField()
    format = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
