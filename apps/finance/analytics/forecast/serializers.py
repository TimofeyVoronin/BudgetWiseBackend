from __future__ import annotations

from rest_framework import serializers


class ForecastingSelectOptionSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ForecastingNumberSelectOptionSerializer(serializers.Serializer):
    value = serializers.IntegerField()
    label = serializers.CharField()


class ForecastingExportSectionOptionSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()


class ForecastingMetaResponseSerializer(serializers.Serializer):
    metric_options = ForecastingSelectOptionSerializer(many=True)
    source_options = ForecastingSelectOptionSerializer(many=True)
    horizon_options = ForecastingNumberSelectOptionSerializer(many=True)
    confidence_options = ForecastingNumberSelectOptionSerializer(many=True)
    model_options = ForecastingSelectOptionSerializer(many=True)
    horizon_steps = serializers.ListField(child=serializers.IntegerField())
    confidence_steps = serializers.ListField(child=serializers.IntegerField())
    export_sections = ForecastingExportSectionOptionSerializer(many=True)
    default_metric = serializers.CharField()
    default_source = serializers.CharField()
    default_horizon_months = serializers.IntegerField()
    default_confidence = serializers.IntegerField()
    default_model = serializers.CharField()
    default_export_sections = serializers.ListField(child=serializers.CharField())
    disclaimer = serializers.CharField()
    chart_footnote = serializers.CharField()


class ForecastingChartPointSerializer(serializers.Serializer):
    month = serializers.CharField()
    label = serializers.CharField()
    value = serializers.FloatField()
    lower_bound = serializers.FloatField(required=False)
    upper_bound = serializers.FloatField(required=False)
    is_forecast = serializers.BooleanField()


class ForecastingDetailRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    month_label = serializers.CharField()
    forecast_rub = serializers.FloatField()
    lower_rub = serializers.FloatField()
    upper_rub = serializers.FloatField()


class ForecastingMetricSummarySerializer(serializers.Serializer):
    total_forecast_rub = serializers.FloatField()
    delta_percent = serializers.FloatField()
    delta_label = serializers.CharField()
    positive_is_good = serializers.BooleanField()


class ForecastingAssumptionsSerializer(serializers.Serializer):
    history_period_label = serializers.CharField()
    source_label = serializers.CharField()
    model_label = serializers.CharField()
    updated_at_label = serializers.CharField()


class ForecastingAlertSerializer(serializers.Serializer):
    type = serializers.CharField()
    icon = serializers.CharField()
    title = serializers.CharField()
    text = serializers.CharField()


class ForecastingProjectionResponseSerializer(serializers.Serializer):
    has_data = serializers.BooleanField()
    has_insufficient_data = serializers.BooleanField()
    has_high_instability = serializers.BooleanField()
    unstable = serializers.BooleanField()
    chart_points = ForecastingChartPointSerializer(many=True)
    detail_rows = ForecastingDetailRowSerializer(many=True)
    metric_summary = ForecastingMetricSummarySerializer()
    assumptions = ForecastingAssumptionsSerializer()
    alert = ForecastingAlertSerializer(required=False, allow_null=True)


class ForecastingExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["pdf", "csv", "xlsx"])
    sections = serializers.ListField(
        child=serializers.ChoiceField(choices=["history", "forecast", "confidence", "parameters"]),
        allow_empty=False,
    )
    metric = serializers.ChoiceField(choices=["income", "expense", "balance"], required=False)
    source = serializers.CharField(required=False, allow_blank=True)
    horizon_months = serializers.IntegerField(required=False)
    confidence = serializers.IntegerField(required=False)
    model = serializers.ChoiceField(choices=["linear", "prophet"], required=False)


class ForecastingExportResponseSerializer(serializers.Serializer):
    download_url = serializers.CharField()
    file_name = serializers.CharField()
    format = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
