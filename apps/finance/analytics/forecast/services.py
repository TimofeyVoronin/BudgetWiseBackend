from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence

from django.db.models import Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.finance.analytics.combined.services import (
    add_months,
    decimal_to_number,
    get_body_value,
    get_first_query_value,
    get_month_bounds,
    get_month_label_from_key,
)
from apps.finance.currencies.conversion import (
    CurrencyConversionService,
    get_currency_conversion_service,
)
from apps.finance.currencies.money import quantize_money
from apps.finance.models import Account, Transaction, TransactionType
from apps.users.app_settings.formatting import get_user_app_today

FORECAST_METRIC_INCOME = "income"
FORECAST_METRIC_EXPENSE = "expense"
FORECAST_METRIC_BALANCE = "balance"
FORECAST_METRICS = {
    FORECAST_METRIC_INCOME,
    FORECAST_METRIC_EXPENSE,
    FORECAST_METRIC_BALANCE,
}

FORECAST_MODEL_LINEAR = "linear"
FORECAST_MODEL_PROPHET = "prophet"
FORECAST_MODELS = {
    FORECAST_MODEL_LINEAR,
    FORECAST_MODEL_PROPHET,
}

FORECAST_EXPORT_FORMATS = {"csv", "xlsx", "pdf"}
FORECAST_EXPORT_SECTIONS = {"history", "forecast", "confidence", "parameters"}

FORECAST_HORIZON_OPTIONS = [1, 3, 6, 12, 24]
FORECAST_CONFIDENCE_OPTIONS = [80, 90, 95, 99]
FORECAST_DEFAULT_METRIC = FORECAST_METRIC_EXPENSE
FORECAST_DEFAULT_SOURCE = "all"
FORECAST_DEFAULT_HORIZON_MONTHS = 6
FORECAST_DEFAULT_CONFIDENCE = 95
FORECAST_DEFAULT_MODEL = FORECAST_MODEL_LINEAR
FORECAST_DEFAULT_EXPORT_SECTIONS = ["history", "forecast", "confidence", "parameters"]
FORECAST_MIN_HISTORY_MONTHS = 6
FORECAST_MAX_HISTORY_MONTHS = 24
FORECAST_INSTABILITY_THRESHOLD = Decimal("0.35")
FORECAST_MIN_INTERVAL_PERCENT = Decimal("0.05")
FORECAST_MIN_INTERVAL_ABS = Decimal("100.00")

FORECAST_DISCLAIMER = (
    "Прогноз носит оценочный характер и не является финансовой рекомендацией. "
    "Расчёт основан на исторических операциях пользователя и может не учитывать будущие события."
)
FORECAST_CHART_FOOTNOTE = (
    "Прогноз построен на основе исторических данных и может не учитывать будущие изменения и события."
)

METRIC_LABELS = {
    FORECAST_METRIC_INCOME: "Доходы",
    FORECAST_METRIC_EXPENSE: "Расходы",
    FORECAST_METRIC_BALANCE: "Баланс",
}

MODEL_LABELS = {
    FORECAST_MODEL_LINEAR: "Линейная регрессия",
    FORECAST_MODEL_PROPHET: "Prophet",
}

CONFIDENCE_Z_SCORES = {
    80: Decimal("1.2816"),
    90: Decimal("1.6449"),
    95: Decimal("1.9600"),
    99: Decimal("2.5758"),
}

SHORT_MONTH_NAMES = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}


@dataclass(frozen=True)
class ForecastingFilters:
    metric: str
    source: str
    horizon_months: int
    confidence: int
    model: str


@dataclass(frozen=True)
class ForecastHistoryPoint:
    month: str
    label: str
    value: Decimal


@dataclass(frozen=True)
class ForecastPoint:
    month: str
    label: str
    value: Decimal
    lower_bound: Decimal
    upper_bound: Decimal


@dataclass(frozen=True)
class ForecastModelResult:
    model: str
    model_label: str
    used_fallback: bool
    fallback_reason: str
    forecast_points: list[ForecastPoint]
    residual_std: Decimal


@dataclass(frozen=True)
class HistorySeries:
    history_points: list[ForecastHistoryPoint]
    date_from: date | None
    date_to: date | None
    source_label: str


class LinearForecastModel:
    """Small deterministic linear model for monthly financial series."""

    def forecast(
        self,
        *,
        history_points: Sequence[ForecastHistoryPoint],
        horizon_months: int,
        confidence: int,
        metric: str,
    ) -> ForecastModelResult:
        values = [point.value for point in history_points]
        forecast_months = get_future_months(last_history_month=history_points[-1].month, horizon_months=horizon_months)
        slope, intercept, residual_std = fit_linear_regression(values)
        forecast_points = []
        for index, month_key in enumerate(forecast_months, start=len(values)):
            raw_value = intercept + slope * Decimal(index)
            value = normalize_forecast_value(raw_value, metric=metric)
            interval_width = calculate_linear_interval_width(
                values=values,
                x_new=Decimal(index),
                residual_std=residual_std,
                confidence=confidence,
            )
            lower_bound, upper_bound = build_bounds(value=value, width=interval_width, metric=metric)
            forecast_points.append(
                ForecastPoint(
                    month=month_key,
                    label=get_short_month_label_from_key(month_key),
                    value=value,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
            )

        return ForecastModelResult(
            model=FORECAST_MODEL_LINEAR,
            model_label=MODEL_LABELS[FORECAST_MODEL_LINEAR],
            used_fallback=False,
            fallback_reason="",
            forecast_points=forecast_points,
            residual_std=residual_std,
        )


class ProphetForecastModel:
    """Optional Prophet model wrapper with safe fallback outside this class."""

    def forecast(
        self,
        *,
        history_points: Sequence[ForecastHistoryPoint],
        horizon_months: int,
        confidence: int,
        metric: str,
    ) -> ForecastModelResult:
        try:
            import pandas as pd
            from prophet import Prophet
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError("Prophet dependency is not available") from exc

        rows = [
            {
                "ds": f"{point.month}-01",
                "y": float(point.value),
            }
            for point in history_points
        ]
        data_frame = pd.DataFrame(rows)
        model = Prophet(
            interval_width=confidence / 100,
            daily_seasonality=False,
            weekly_seasonality=False,
            yearly_seasonality=len(history_points) >= 18,
        )
        model.fit(data_frame)
        future = model.make_future_dataframe(
            periods=horizon_months,
            freq="MS",
            include_history=False,
        )
        forecast = model.predict(future)

        forecast_points = []
        for row in forecast.tail(horizon_months).itertuples(index=False):
            month_date = row.ds.date() if hasattr(row.ds, "date") else row.ds
            month_key = f"{month_date.year:04d}-{month_date.month:02d}"
            value = normalize_forecast_value(Decimal(str(row.yhat)), metric=metric)
            lower_bound = normalize_forecast_value(Decimal(str(row.yhat_lower)), metric=metric)
            upper_bound = normalize_forecast_value(Decimal(str(row.yhat_upper)), metric=metric)
            if lower_bound > upper_bound:
                lower_bound, upper_bound = upper_bound, lower_bound
            forecast_points.append(
                ForecastPoint(
                    month=month_key,
                    label=get_short_month_label_from_key(month_key),
                    value=value,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                )
            )

        residual_std = calculate_residual_std_from_series([point.value for point in history_points])
        return ForecastModelResult(
            model=FORECAST_MODEL_PROPHET,
            model_label=MODEL_LABELS[FORECAST_MODEL_PROPHET],
            used_fallback=False,
            fallback_reason="",
            forecast_points=forecast_points,
            residual_std=residual_std,
        )


class ForecastingService:
    def __init__(
        self,
        *,
        converter: CurrencyConversionService | None = None,
    ) -> None:
        self.converter = converter
        self.linear_model = LinearForecastModel()
        self.prophet_model = ProphetForecastModel()

    def build_meta(self, *, user) -> dict:
        active_accounts = list(
            Account.objects
            .filter(user=user, is_active=True, is_archived=False)
            .order_by("-is_default", "name", "id")
        )
        return {
            "metric_options": [
                {"value": FORECAST_METRIC_INCOME, "label": "Доходы"},
                {"value": FORECAST_METRIC_EXPENSE, "label": "Расходы"},
                {"value": FORECAST_METRIC_BALANCE, "label": "Баланс"},
            ],
            "source_options": [
                {"value": "all", "label": "Все счета"},
                *[
                    {"value": str(account.id), "label": account.name}
                    for account in active_accounts
                ],
            ],
            "horizon_options": [
                {"value": value, "label": format_horizon_label(value)}
                for value in FORECAST_HORIZON_OPTIONS
            ],
            "confidence_options": [
                {"value": value, "label": f"{value}%"}
                for value in FORECAST_CONFIDENCE_OPTIONS
            ],
            "model_options": [
                {"value": FORECAST_MODEL_LINEAR, "label": MODEL_LABELS[FORECAST_MODEL_LINEAR]},
                {"value": FORECAST_MODEL_PROPHET, "label": MODEL_LABELS[FORECAST_MODEL_PROPHET]},
            ],
            "horizon_steps": FORECAST_HORIZON_OPTIONS,
            "confidence_steps": FORECAST_CONFIDENCE_OPTIONS,
            "export_sections": [
                {"id": "history", "label": "Включить историю", "icon": "mdi-history"},
                {"id": "forecast", "label": "Включить прогноз", "icon": "mdi-chart-line"},
                {"id": "confidence", "label": "Включить интервал доверия", "icon": "mdi-shield-check"},
                {"id": "parameters", "label": "Включить параметры модели", "icon": "mdi-tune"},
            ],
            "default_metric": FORECAST_DEFAULT_METRIC,
            "default_source": FORECAST_DEFAULT_SOURCE,
            "default_horizon_months": FORECAST_DEFAULT_HORIZON_MONTHS,
            "default_confidence": FORECAST_DEFAULT_CONFIDENCE,
            "default_model": FORECAST_DEFAULT_MODEL,
            "default_export_sections": FORECAST_DEFAULT_EXPORT_SECTIONS,
            "disclaimer": FORECAST_DISCLAIMER,
            "chart_footnote": FORECAST_CHART_FOOTNOTE,
        }

    def build_projection(self, *, user, filters: ForecastingFilters) -> dict:
        converter = self.converter or get_currency_conversion_service(
            user=user,
            display_currency="RUB",
        )
        history = build_history_series(user=user, filters=filters, converter=converter)
        assumptions_base = build_assumptions(
            history=history,
            filters=filters,
            model_label=MODEL_LABELS.get(filters.model, filters.model),
        )

        if len(history.history_points) < FORECAST_MIN_HISTORY_MONTHS:
            return build_empty_projection(
                history=history,
                filters=filters,
                assumptions=assumptions_base,
                alert={
                    "type": "warning",
                    "icon": "mdi-alert-outline",
                    "title": "Недостаточно данных для прогноза",
                    "text": (
                        "Для построения прогноза нужно минимум "
                        f"{FORECAST_MIN_HISTORY_MONTHS} завершённых месяцев истории."
                    ),
                },
                has_insufficient_data=True,
            )

        model_result = self.run_model(
            history_points=history.history_points,
            filters=filters,
        )
        has_high_instability = detect_high_instability(
            history_points=history.history_points,
            residual_std=model_result.residual_std,
        )
        chart_points = build_chart_points(
            history_points=history.history_points,
            forecast_points=model_result.forecast_points,
        )
        detail_rows = build_detail_rows(model_result.forecast_points)
        metric_summary = build_metric_summary(
            history_points=history.history_points,
            forecast_points=model_result.forecast_points,
            metric=filters.metric,
        )
        assumptions = build_assumptions(
            history=history,
            filters=filters,
            model_label=model_result.model_label,
        )
        alert = build_projection_alert(
            used_fallback=model_result.used_fallback,
            fallback_reason=model_result.fallback_reason,
            has_high_instability=has_high_instability,
        )

        return {
            "has_data": True,
            "has_insufficient_data": False,
            "has_high_instability": has_high_instability,
            "unstable": has_high_instability,
            "chart_points": chart_points,
            "detail_rows": detail_rows,
            "metric_summary": metric_summary,
            "assumptions": assumptions,
            "alert": alert,
        }

    def run_model(
        self,
        *,
        history_points: Sequence[ForecastHistoryPoint],
        filters: ForecastingFilters,
    ) -> ForecastModelResult:
        if filters.model == FORECAST_MODEL_PROPHET:
            try:
                return self.prophet_model.forecast(
                    history_points=history_points,
                    horizon_months=filters.horizon_months,
                    confidence=filters.confidence,
                    metric=filters.metric,
                )
            except Exception as exc:
                fallback = self.linear_model.forecast(
                    history_points=history_points,
                    horizon_months=filters.horizon_months,
                    confidence=filters.confidence,
                    metric=filters.metric,
                )
                return ForecastModelResult(
                    model=FORECAST_MODEL_LINEAR,
                    model_label=f"{MODEL_LABELS[FORECAST_MODEL_LINEAR]} (fallback после ошибки Prophet)",
                    used_fallback=True,
                    fallback_reason=str(exc),
                    forecast_points=fallback.forecast_points,
                    residual_std=fallback.residual_std,
                )

        return self.linear_model.forecast(
            history_points=history_points,
            horizon_months=filters.horizon_months,
            confidence=filters.confidence,
            metric=filters.metric,
        )


def build_forecasting_meta(*, user) -> dict:
    return ForecastingService().build_meta(user=user)


def build_forecasting_projection(*, user, filters: ForecastingFilters) -> dict:
    return ForecastingService().build_projection(user=user, filters=filters)


def build_forecasting_filters_from_query(*, user, query_params) -> ForecastingFilters:
    metric = normalize_metric(get_first_query_value(query_params, "metric"))
    source = normalize_source(user=user, raw_source=get_first_query_value(query_params, "source"))
    horizon_months = normalize_horizon(get_first_query_value(query_params, "horizon_months", "horizonMonths"))
    confidence = normalize_confidence(get_first_query_value(query_params, "confidence"))
    model = normalize_model(get_first_query_value(query_params, "model"))
    return ForecastingFilters(
        metric=metric,
        source=source,
        horizon_months=horizon_months,
        confidence=confidence,
        model=model,
    )


def build_forecasting_filters_from_body(*, user, payload: Mapping[str, object]) -> ForecastingFilters:
    metric = normalize_metric(get_body_value(payload, "metric"))
    source = normalize_source(user=user, raw_source=get_body_value(payload, "source"))
    horizon_months = normalize_horizon(get_body_value(payload, "horizon_months", "horizonMonths"))
    confidence = normalize_confidence(get_body_value(payload, "confidence"))
    model = normalize_model(get_body_value(payload, "model"))
    return ForecastingFilters(
        metric=metric,
        source=source,
        horizon_months=horizon_months,
        confidence=confidence,
        model=model,
    )


def build_history_series(
    *,
    user,
    filters: ForecastingFilters,
    converter: CurrencyConversionService,
) -> HistorySeries:
    today = get_user_app_today(user)
    first_current_month = date(today.year, today.month, 1)
    history_end = add_months(first_current_month, -1)
    history_end = get_month_bounds(history_end.year, history_end.month)[1]

    base_queryset = Transaction.objects.filter(user=user)
    if filters.source != "all":
        base_queryset = base_queryset.filter(account_id=int(filters.source))

    earliest_date = base_queryset.filter(operation_date__lte=history_end).aggregate(
        value=Min("operation_date")
    )["value"]
    if earliest_date is None:
        source_label = resolve_source_label(user=user, source=filters.source)
        return HistorySeries(history_points=[], date_from=None, date_to=None, source_label=source_label)

    first_month = date(earliest_date.year, earliest_date.month, 1)
    max_first_month = add_months(date(history_end.year, history_end.month, 1), -(FORECAST_MAX_HISTORY_MONTHS - 1))
    history_start = max(first_month, max_first_month)

    month_keys = build_month_keys(history_start, history_end)
    monthly_values = {
        month_key: {
            FORECAST_METRIC_INCOME: Decimal("0.00"),
            FORECAST_METRIC_EXPENSE: Decimal("0.00"),
        }
        for month_key in month_keys
    }

    rows = (
        base_queryset
        .filter(operation_date__gte=history_start, operation_date__lte=history_end)
        .annotate(month=TruncMonth("operation_date"))
        .values("month", "type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )
    for row in rows:
        month_value = row["month"]
        month_date = month_value.date() if hasattr(month_value, "date") else month_value
        month_key = f"{month_date.year:04d}-{month_date.month:02d}"
        transaction_type = row["type"]
        if month_key not in monthly_values or transaction_type not in monthly_values[month_key]:
            continue
        converted = converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        monthly_values[month_key][transaction_type] += converted

    history_points = []
    for month_key in month_keys:
        values = monthly_values[month_key]
        metric_value = resolve_metric_value(values, metric=filters.metric)
        history_points.append(
            ForecastHistoryPoint(
                month=month_key,
                label=get_short_month_label_from_key(month_key),
                value=quantize_money(metric_value),
            )
        )

    return HistorySeries(
        history_points=history_points,
        date_from=history_start,
        date_to=history_end,
        source_label=resolve_source_label(user=user, source=filters.source),
    )


def normalize_metric(value: object | None) -> str:
    metric = str(value or FORECAST_DEFAULT_METRIC).strip().lower()
    if metric not in FORECAST_METRICS:
        raise ValidationError({"metric": "Недопустимая метрика прогноза."})
    return metric


def normalize_source(*, user, raw_source: object | None) -> str:
    source = str(raw_source or FORECAST_DEFAULT_SOURCE).strip()
    if not source or source == FORECAST_DEFAULT_SOURCE:
        return FORECAST_DEFAULT_SOURCE
    try:
        account_id = int(source)
    except (TypeError, ValueError):
        raise ValidationError({"source": "Источник должен быть 'all' или id счёта."})

    exists = Account.objects.filter(user=user, id=account_id).exists()
    if not exists:
        raise ValidationError({"source": "Счёт не найден или недоступен пользователю."})
    return str(account_id)


def normalize_horizon(value: object | None) -> int:
    try:
        horizon = int(value or FORECAST_DEFAULT_HORIZON_MONTHS)
    except (TypeError, ValueError):
        raise ValidationError({"horizon_months": "Горизонт прогноза должен быть числом."})
    if horizon not in FORECAST_HORIZON_OPTIONS:
        raise ValidationError({"horizon_months": "Недопустимый горизонт прогноза."})
    return horizon


def normalize_confidence(value: object | None) -> int:
    try:
        confidence = int(value or FORECAST_DEFAULT_CONFIDENCE)
    except (TypeError, ValueError):
        raise ValidationError({"confidence": "Уровень доверия должен быть числом."})
    if confidence not in FORECAST_CONFIDENCE_OPTIONS:
        raise ValidationError({"confidence": "Недопустимый уровень доверия."})
    return confidence


def normalize_model(value: object | None) -> str:
    model = str(value or FORECAST_DEFAULT_MODEL).strip().lower()
    if model not in FORECAST_MODELS:
        raise ValidationError({"model": "Недопустимая модель прогнозирования."})
    return model


def build_month_keys(date_from: date, date_to: date) -> list[str]:
    current = date(date_from.year, date_from.month, 1)
    last = date(date_to.year, date_to.month, 1)
    result = []
    while current <= last:
        result.append(f"{current.year:04d}-{current.month:02d}")
        current = add_months(current, 1)
    return result


def get_future_months(*, last_history_month: str, horizon_months: int) -> list[str]:
    year, month = parse_month_key(last_history_month)
    start = add_months(date(year, month, 1), 1)
    return [
        f"{add_months(start, offset).year:04d}-{add_months(start, offset).month:02d}"
        for offset in range(horizon_months)
    ]


def parse_month_key(month_key: str) -> tuple[int, int]:
    year_raw, month_raw = month_key.split("-", 1)
    return int(year_raw), int(month_raw)


def resolve_metric_value(values: Mapping[str, Decimal], *, metric: str) -> Decimal:
    income = values.get(FORECAST_METRIC_INCOME, Decimal("0.00"))
    expense = values.get(FORECAST_METRIC_EXPENSE, Decimal("0.00"))
    if metric == FORECAST_METRIC_INCOME:
        return income
    if metric == FORECAST_METRIC_EXPENSE:
        return expense
    return income - expense


def resolve_source_label(*, user, source: str) -> str:
    if source == "all":
        return "Все счета"
    account = Account.objects.filter(user=user, id=int(source)).first()
    return account.name if account else "Выбранный счёт"


def fit_linear_regression(values: Sequence[Decimal]) -> tuple[Decimal, Decimal, Decimal]:
    n = len(values)
    if n == 1:
        return Decimal("0.00"), values[0], Decimal("0.00")

    x_values = [Decimal(index) for index in range(n)]
    x_mean = sum(x_values, Decimal("0.00")) / Decimal(n)
    y_mean = sum(values, Decimal("0.00")) / Decimal(n)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        slope = Decimal("0.00")
    else:
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values)) / denominator
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in x_values]
    residuals = [value - expected for value, expected in zip(values, fitted)]
    if n > 2:
        residual_variance = sum((residual ** 2 for residual in residuals), Decimal("0.00")) / Decimal(n - 2)
        residual_std = decimal_sqrt(residual_variance)
    else:
        residual_std = Decimal("0.00")
    return slope, intercept, residual_std


def calculate_linear_interval_width(
    *,
    values: Sequence[Decimal],
    x_new: Decimal,
    residual_std: Decimal,
    confidence: int,
) -> Decimal:
    n = len(values)
    average_abs = calculate_average_abs(values)
    min_width = max(average_abs * FORECAST_MIN_INTERVAL_PERCENT, FORECAST_MIN_INTERVAL_ABS)
    if n < 2 or residual_std == 0:
        return quantize_money(min_width)

    x_values = [Decimal(index) for index in range(n)]
    x_mean = sum(x_values, Decimal("0.00")) / Decimal(n)
    sxx = sum((x - x_mean) ** 2 for x in x_values)
    if sxx == 0:
        leverage = Decimal("1.00")
    else:
        leverage = Decimal("1.00") + (Decimal("1.00") / Decimal(n)) + (((x_new - x_mean) ** 2) / sxx)
    z_score = CONFIDENCE_Z_SCORES[confidence]
    width = z_score * residual_std * decimal_sqrt(leverage)
    return quantize_money(max(width, min_width))


def calculate_residual_std_from_series(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        return Decimal("0.00")
    float_values = [float(value) for value in values]
    return Decimal(str(pstdev(float_values)))


def calculate_average_abs(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.00")
    return sum((abs(value) for value in values), Decimal("0.00")) / Decimal(len(values))


def build_bounds(*, value: Decimal, width: Decimal, metric: str) -> tuple[Decimal, Decimal]:
    lower = value - width
    upper = value + width
    if metric in {FORECAST_METRIC_INCOME, FORECAST_METRIC_EXPENSE}:
        lower = max(lower, Decimal("0.00"))
    return quantize_money(lower), quantize_money(max(upper, lower))


def normalize_forecast_value(value: Decimal, *, metric: str) -> Decimal:
    if metric in {FORECAST_METRIC_INCOME, FORECAST_METRIC_EXPENSE}:
        value = max(value, Decimal("0.00"))
    return quantize_money(value)


def detect_high_instability(
    *,
    history_points: Sequence[ForecastHistoryPoint],
    residual_std: Decimal,
) -> bool:
    values = [point.value for point in history_points]
    average_abs = calculate_average_abs(values)
    if average_abs == 0:
        return False
    variation = residual_std / average_abs
    return variation >= FORECAST_INSTABILITY_THRESHOLD


def build_chart_points(
    *,
    history_points: Sequence[ForecastHistoryPoint],
    forecast_points: Sequence[ForecastPoint],
) -> list[dict]:
    points = [
        {
            "month": point.month,
            "label": point.label,
            "value": decimal_to_number(point.value),
            "is_forecast": False,
        }
        for point in history_points
    ]
    points.extend(
        {
            "month": point.month,
            "label": point.label,
            "value": decimal_to_number(point.value),
            "lower_bound": decimal_to_number(point.lower_bound),
            "upper_bound": decimal_to_number(point.upper_bound),
            "is_forecast": True,
        }
        for point in forecast_points
    )
    return points


def build_detail_rows(forecast_points: Sequence[ForecastPoint]) -> list[dict]:
    return [
        {
            "id": point.month,
            "month_label": point.label,
            "forecast_rub": decimal_to_number(point.value),
            "lower_rub": decimal_to_number(point.lower_bound),
            "upper_rub": decimal_to_number(point.upper_bound),
        }
        for point in forecast_points
    ]


def build_metric_summary(
    *,
    history_points: Sequence[ForecastHistoryPoint],
    forecast_points: Sequence[ForecastPoint],
    metric: str,
) -> dict:
    total_forecast = sum((point.value for point in forecast_points), Decimal("0.00"))
    horizon = len(forecast_points)
    baseline_points = history_points[-horizon:] if horizon else []
    if len(baseline_points) < horizon and history_points:
        average = sum((point.value for point in history_points), Decimal("0.00")) / Decimal(len(history_points))
        baseline_total = average * Decimal(horizon)
    else:
        baseline_total = sum((point.value for point in baseline_points), Decimal("0.00"))
    delta_percent = calculate_delta_percent(total_forecast, baseline_total)
    return {
        "total_forecast_rub": decimal_to_number(quantize_money(total_forecast)),
        "delta_percent": decimal_to_number(delta_percent),
        "delta_label": "к среднему за предыдущий период",
        "positive_is_good": metric != FORECAST_METRIC_EXPENSE,
    }


def build_assumptions(
    *,
    history: HistorySeries,
    filters: ForecastingFilters,
    model_label: str,
) -> dict:
    return {
        "history_period_label": build_history_period_label(history),
        "source_label": history.source_label,
        "model_label": model_label,
        "updated_at_label": format_russian_date(timezone.localdate()),
    }


def build_empty_projection(
    *,
    history: HistorySeries,
    filters: ForecastingFilters,
    assumptions: dict,
    alert: dict | None,
    has_insufficient_data: bool,
) -> dict:
    return {
        "has_data": False,
        "has_insufficient_data": has_insufficient_data,
        "has_high_instability": False,
        "unstable": has_insufficient_data,
        "chart_points": [
            {
                "month": point.month,
                "label": point.label,
                "value": decimal_to_number(point.value),
                "is_forecast": False,
            }
            for point in history.history_points
        ],
        "detail_rows": [],
        "metric_summary": {
            "total_forecast_rub": 0.0,
            "delta_percent": 0.0,
            "delta_label": "к среднему за предыдущий период",
            "positive_is_good": filters.metric != FORECAST_METRIC_EXPENSE,
        },
        "assumptions": assumptions,
        "alert": alert,
    }


def build_projection_alert(
    *,
    used_fallback: bool,
    fallback_reason: str,
    has_high_instability: bool,
) -> dict | None:
    if has_high_instability:
        return {
            "type": "warning",
            "icon": "mdi-alert-outline",
            "title": "Низкая точность прогноза",
            "text": "Исторические данные нестабильны, поэтому интервал прогноза может быть широким.",
        }
    if used_fallback:
        return {
            "type": "info",
            "icon": "mdi-information-outline",
            "title": "Использована резервная модель",
            "text": "Prophet недоступен или завершился ошибкой, поэтому прогноз построен линейной моделью.",
        }
    return None


def build_history_period_label(history: HistorySeries) -> str:
    if not history.date_from or not history.date_to:
        return "Нет завершённой истории"
    return f"{get_short_month_label(history.date_from)} — {get_short_month_label(history.date_to)}"


def get_short_month_label(value: date) -> str:
    return f"{SHORT_MONTH_NAMES[value.month]} {value.year}"


def get_short_month_label_from_key(month_key: str) -> str:
    year, month = parse_month_key(month_key)
    return f"{SHORT_MONTH_NAMES[month]} {year}"


def format_russian_date(value: date) -> str:
    return f"{value.day} {get_month_label_from_key(f'{value.year:04d}-{value.month:02d}').split()[0].lower()} {value.year}"


def format_horizon_label(value: int) -> str:
    if value == 1:
        return "1 месяц"
    if value in {3, 6, 12}:
        return f"{value} месяцев"
    return f"{value} месяца"


def calculate_delta_percent(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        if current == 0:
            return Decimal("0.00")
        return Decimal("100.00") if current > 0 else Decimal("-100.00")
    return ((current - previous) / abs(previous) * Decimal("100.00")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def decimal_sqrt(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0.00")
    return Decimal(str(math.sqrt(float(value))))
