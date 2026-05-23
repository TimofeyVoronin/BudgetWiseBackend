from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum
from django.utils import timezone

from apps.finance.financial_calendar_exporters import (
    FINANCIAL_CALENDAR_EXPORT_FORMATS,
    build_financial_calendar_download_url,
    build_financial_calendar_export_file,
    normalize_financial_calendar_export_columns,
    normalize_financial_calendar_export_format,
)
from apps.finance.models import (
    Account,
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)
from apps.users.app_settings.services import TIMEZONE_OPTIONS, is_valid_timezone
from apps.users.app_settings.formatting import (
    AppSettingsFormattingContext,
    LEGACY_TIMEZONE_OFFSETS,
    build_app_formatting_context,
    format_app_date,
    format_app_money,
)


FINANCIAL_CALENDAR_EVENT_INCOME = "income"
FINANCIAL_CALENDAR_EVENT_EXPENSE = "expense"
FINANCIAL_CALENDAR_EVENT_TRANSFER = "transfer"
FINANCIAL_CALENDAR_EVENT_REMINDER = "reminder"

FINANCIAL_CALENDAR_EVENT_TYPES = {
    FINANCIAL_CALENDAR_EVENT_INCOME,
    FINANCIAL_CALENDAR_EVENT_EXPENSE,
    FINANCIAL_CALENDAR_EVENT_TRANSFER,
    FINANCIAL_CALENDAR_EVENT_REMINDER,
}

FINANCIAL_CALENDAR_STATUS_CONFIRMED = "confirmed"
FINANCIAL_CALENDAR_STATUS_PENDING = "pending"

FINANCIAL_CALENDAR_RISK_SAFE = "safe"
FINANCIAL_CALENDAR_RISK_CAUTION = "caution"
FINANCIAL_CALENDAR_RISK_RISK = "risk"

DEFAULT_FINANCIAL_CALENDAR_TIMEZONE = "Asia/Krasnoyarsk"
FINANCIAL_CALENDAR_TIMEZONES = TIMEZONE_OPTIONS

MAX_FINANCIAL_CALENDAR_RANGE_DAYS = 370


@dataclass(frozen=True)
class FinancialCalendarQuery:
    year: int
    month: int
    date_from: date
    date_to: date
    grid_date_from: date
    grid_date_to: date
    account_ids: list[int]
    event_types: set[str]
    timezone_value: str


@dataclass(frozen=True)
class FinancialCalendarProjection:
    opening_balance: Decimal
    day_forecasts: list[dict]


def resolve_month_grid(year: int, month: int) -> tuple[date, date]:
    first_day = date(year, month, 1)
    _, last_day_number = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_number)

    grid_start = first_day - timedelta(days=first_day.weekday())
    grid_end = last_day + timedelta(days=6 - last_day.weekday())

    return grid_start, grid_end


def build_financial_calendar_month(
    *,
    user,
    year: int,
    month: int,
    account_ids: list[int] | None = None,
    event_types: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timezone_value: str | None = None,
) -> dict:
    formatting_context = build_app_formatting_context(user, timezone_value=timezone_value)
    query = build_financial_calendar_query(
        user=user,
        year=year,
        month=month,
        account_ids=account_ids,
        event_types=event_types,
        date_from=date_from,
        date_to=date_to,
        timezone_value=formatting_context.timezone_name,
    )

    events = get_financial_calendar_events(
        user=user,
        date_from=query.date_from,
        date_to=query.date_to,
        account_ids=query.account_ids,
        event_types=query.event_types,
        formatting_context=formatting_context,
    )
    projection = calculate_financial_calendar_projection(
        user=user,
        date_from=query.date_from,
        date_to=query.date_to,
        account_ids=query.account_ids,
        events=events,
        formatting_context=formatting_context,
    )
    mark_sharp_change_events(
        events=events,
        opening_balance=projection.opening_balance,
    )
    cells = build_financial_calendar_cells(
        year=year,
        month=month,
        day_forecasts=projection.day_forecasts,
        events=events,
        formatting_context=formatting_context,
        user=user,
    )

    today = timezone.localdate(timezone=formatting_context.timezone)

    return {
        "year": year,
        "month": month,
        "todayIso": today.isoformat(),
        "todayLabel": format_app_date(today, formatting_context),
        "openingBalanceRub": format_money(projection.opening_balance),
        "openingBalanceLabel": format_app_money(projection.opening_balance, formatting_context, user=user, currency_code="RUB"),
        "cells": cells,
        "events": events,
        "dayForecasts": projection.day_forecasts,
        "cashGap": find_cash_gap_range(projection.day_forecasts),
    }


def build_financial_calendar_query(
    *,
    user,
    year: int,
    month: int,
    account_ids: list[int] | None = None,
    event_types: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timezone_value: str | None = None,
) -> FinancialCalendarQuery:
    if month < 1 or month > 12:
        raise ValueError("Месяц должен быть от 1 до 12.")

    grid_date_from, grid_date_to = resolve_month_grid(year, month)
    resolved_date_from = date_from or grid_date_from
    resolved_date_to = date_to or grid_date_to

    if resolved_date_from > resolved_date_to:
        raise ValueError("dateFrom не может быть позже dateTo.")

    if (resolved_date_to - resolved_date_from).days > MAX_FINANCIAL_CALENDAR_RANGE_DAYS:
        raise ValueError(
            f"Период календаря не должен превышать {MAX_FINANCIAL_CALENDAR_RANGE_DAYS} дней."
        )

    resolved_account_ids = get_financial_calendar_account_ids(user, account_ids)
    resolved_event_types = set(event_types or FINANCIAL_CALENDAR_EVENT_TYPES)
    invalid_event_types = resolved_event_types - FINANCIAL_CALENDAR_EVENT_TYPES

    if invalid_event_types:
        allowed_values = ", ".join(sorted(FINANCIAL_CALENDAR_EVENT_TYPES))
        raise ValueError(f"Недопустимые типы событий. Допустимые значения: {allowed_values}.")

    resolved_timezone_value = timezone_value or DEFAULT_FINANCIAL_CALENDAR_TIMEZONE
    if not is_valid_financial_calendar_timezone(resolved_timezone_value):
        raise ValueError("Недопустимый часовой пояс календаря.")

    return FinancialCalendarQuery(
        year=year,
        month=month,
        date_from=resolved_date_from,
        date_to=resolved_date_to,
        grid_date_from=grid_date_from,
        grid_date_to=grid_date_to,
        account_ids=resolved_account_ids,
        event_types=resolved_event_types,
        timezone_value=resolved_timezone_value,
    )


def is_valid_financial_calendar_timezone(value: str) -> bool:
    return is_valid_timezone(value) or value in LEGACY_TIMEZONE_OFFSETS


def get_context_today(context: AppSettingsFormattingContext) -> date:
    return timezone.localdate(timezone=context.timezone)


def get_calendar_money_label(value: Decimal | None, context: AppSettingsFormattingContext, user) -> str | None:
    return format_app_money(value, context, user=user, currency_code="RUB")


def get_financial_calendar_account_ids(user, account_ids: list[int] | None = None) -> list[int]:
    queryset = Account.objects.filter(
        user=user,
        is_active=True,
        is_archived=False,
    )

    if account_ids:
        owned_ids = set(queryset.filter(id__in=account_ids).values_list("id", flat=True))
        requested_ids = set(account_ids)

        if owned_ids != requested_ids:
            raise ValueError("Один или несколько счетов не найдены или недоступны.")

        return sorted(owned_ids)

    return list(queryset.order_by("id").values_list("id", flat=True))


def get_accounts_opening_balance(user, account_ids: list[int]) -> Decimal:
    """Return the current stored balance for selected accounts.

    Account.balance is the current balance maintained by transaction services.
    The financial calendar uses this value as the anchor point and derives
    historical/future opening balances from confirmed and planned events.
    """
    if not account_ids:
        return Decimal("0.00")

    value = (
        Account.objects
        .filter(user=user, id__in=account_ids, is_active=True, is_archived=False)
        .aggregate(total=Sum("balance"))
        .get("total")
    )
    return value or Decimal("0.00")


def get_actual_transactions_delta(
    *,
    user,
    account_ids: list[int],
    date_from: date,
    date_to: date,
) -> Decimal:
    if not account_ids or date_from > date_to:
        return Decimal("0.00")

    queryset = Transaction.objects.filter(
        user=user,
        account_id__in=account_ids,
        operation_date__gte=date_from,
        operation_date__lte=date_to,
    )
    income = (
        queryset
        .filter(type=TransactionType.INCOME)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0.00")
    )
    expense = (
        queryset
        .filter(type=TransactionType.EXPENSE)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0.00")
    )
    return income - expense


def get_planned_transactions_delta(
    *,
    user,
    account_ids: list[int],
    date_from: date,
    date_to: date,
) -> Decimal:
    if not account_ids or date_from > date_to:
        return Decimal("0.00")

    queryset = PlannedTransaction.objects.filter(
        user=user,
        account_id__in=account_ids,
        planned_date__gte=date_from,
        planned_date__lte=date_to,
        include_in_forecast=True,
        status__in=[PlannedStatus.PENDING, PlannedStatus.CONFIRMED],
    )
    income = (
        queryset
        .filter(type=TransactionType.INCOME)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0.00")
    )
    expense = (
        queryset
        .filter(type=TransactionType.EXPENSE)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0.00")
    )
    return income - expense


def calculate_projection_opening_balance(
    *,
    user,
    account_ids: list[int],
    date_from: date,
    today: date,
) -> Decimal:
    current_balance = get_accounts_opening_balance(user, account_ids)

    if date_from <= today:
        actual_delta = get_actual_transactions_delta(
            user=user,
            account_ids=account_ids,
            date_from=date_from,
            date_to=today,
        )
        return current_balance - actual_delta

    planned_delta = get_planned_transactions_delta(
        user=user,
        account_ids=account_ids,
        date_from=today + timedelta(days=1),
        date_to=date_from - timedelta(days=1),
    )
    return current_balance + planned_delta


def get_financial_calendar_events(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: list[int],
    event_types: set[str] | None = None,
    formatting_context: AppSettingsFormattingContext | None = None,
) -> list[dict]:
    if not account_ids:
        return []

    event_types = event_types or FINANCIAL_CALENDAR_EVENT_TYPES
    formatting_context = formatting_context or get_default_financial_calendar_context(user)
    events: list[dict] = []

    if FINANCIAL_CALENDAR_EVENT_INCOME in event_types or FINANCIAL_CALENDAR_EVENT_EXPENSE in event_types:
        transaction_queryset = (
            Transaction.objects
            .select_related("account", "category")
            .filter(
                user=user,
                account_id__in=account_ids,
                operation_date__gte=date_from,
                operation_date__lte=date_to,
            )
            .order_by("operation_date", "id")
        )

        for transaction in transaction_queryset:
            event_type = transaction.type
            if event_type not in event_types:
                continue
            events.append(transaction_to_calendar_event(transaction, formatting_context, user))

    if FINANCIAL_CALENDAR_EVENT_INCOME in event_types or FINANCIAL_CALENDAR_EVENT_EXPENSE in event_types:
        planned_queryset = (
            PlannedTransaction.objects
            .select_related("account", "category")
            .filter(
                user=user,
                account_id__in=account_ids,
                planned_date__gte=date_from,
                planned_date__lte=date_to,
                include_in_forecast=True,
                status__in=[PlannedStatus.PENDING, PlannedStatus.CONFIRMED],
            )
            .order_by("planned_date", "id")
        )

        for planned in planned_queryset:
            event_type = planned.type
            if event_type not in event_types:
                continue
            events.append(planned_to_calendar_event(planned, formatting_context, user))

    events.sort(key=lambda item: (item["date"], item["status"], item["id"]))
    return events


def get_default_financial_calendar_context(user) -> AppSettingsFormattingContext:
    return build_app_formatting_context(user)


def transaction_to_calendar_event(transaction: Transaction, formatting_context: AppSettingsFormattingContext, user) -> dict:
    signed_amount = get_signed_amount(transaction.type, transaction.amount)
    title = transaction.description.strip() if transaction.description else transaction.category.name

    return {
        "id": f"tx-{transaction.id}",
        "sourceId": transaction.id,
        "sourceType": "transaction",
        "date": transaction.operation_date.isoformat(),
        "dateLabel": format_app_date(transaction.operation_date, formatting_context),
        "type": transaction.type,
        "title": title,
        "subtitle": transaction.category.name,
        "amountRub": format_money(signed_amount),
        "amountLabel": get_calendar_money_label(signed_amount, formatting_context, user),
        "accountId": transaction.account_id,
        "accountName": transaction.account.name,
        "status": FINANCIAL_CALENDAR_STATUS_CONFIRMED,
        "isSharpChange": False,
    }


def planned_to_calendar_event(planned: PlannedTransaction, formatting_context: AppSettingsFormattingContext, user) -> dict:
    signed_amount = get_signed_amount(planned.type, planned.amount)

    return {
        "id": f"planned-{planned.id}",
        "sourceId": planned.id,
        "sourceType": "planned_transaction",
        "date": planned.planned_date.isoformat(),
        "dateLabel": format_app_date(planned.planned_date, formatting_context),
        "type": planned.type,
        "title": planned.name,
        "subtitle": planned.category.name,
        "amountRub": format_money(signed_amount),
        "amountLabel": get_calendar_money_label(signed_amount, formatting_context, user),
        "accountId": planned.account_id,
        "accountName": planned.account.name,
        "status": FINANCIAL_CALENDAR_STATUS_PENDING,
        "isSharpChange": False,
    }


def calculate_financial_calendar_projection(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: list[int],
    events: list[dict],
    formatting_context: AppSettingsFormattingContext | None = None,
) -> FinancialCalendarProjection:
    formatting_context = formatting_context or get_default_financial_calendar_context(user)
    today = get_context_today(formatting_context)
    opening_balance = calculate_projection_opening_balance(
        user=user,
        account_ids=account_ids,
        date_from=date_from,
        today=today,
    )
    events_by_date: dict[str, list[dict]] = {}

    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)

    current_date = date_from
    forecast_balance = opening_balance
    actual_balance = opening_balance
    rows: list[dict] = []

    while current_date <= date_to:
        iso = current_date.isoformat()
        day_events = events_by_date.get(iso, [])
        confirmed_delta = sum_event_amounts(
            event for event in day_events if event["status"] == FINANCIAL_CALENDAR_STATUS_CONFIRMED
        )
        pending_delta = sum_event_amounts(
            event for event in day_events if event["status"] == FINANCIAL_CALENDAR_STATUS_PENDING
        )
        total_delta = confirmed_delta + pending_delta

        if current_date <= today:
            actual_balance += confirmed_delta
            forecast_balance += total_delta
            actual_balance_value = actual_balance
        else:
            forecast_balance += total_delta
            actual_balance_value = None

        is_past = current_date < today
        is_today = current_date == today

        rows.append(
            {
                "date": iso,
                "dateLabel": format_app_date(current_date, formatting_context),
                "actualBalanceRub": format_money(actual_balance_value) if actual_balance_value is not None else None,
                "actualBalanceLabel": get_calendar_money_label(actual_balance_value, formatting_context, user),
                "forecastBalanceRub": format_money(forecast_balance),
                "forecastBalanceLabel": get_calendar_money_label(forecast_balance, formatting_context, user),
                "totalDelta": format_money(total_delta),
                "totalDeltaLabel": get_calendar_money_label(total_delta, formatting_context, user),
                "hasEvents": bool(day_events),
                "riskLevel": get_calendar_risk_level(
                    opening_balance=opening_balance,
                    forecast_balance=forecast_balance,
                    total_delta=total_delta,
                ),
                "isToday": is_today,
                "isPast": is_past,
            }
        )
        current_date += timedelta(days=1)

    return FinancialCalendarProjection(
        opening_balance=opening_balance,
        day_forecasts=rows,
    )


def calculate_financial_calendar_day_forecasts(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: list[int],
    events: list[dict],
    formatting_context: AppSettingsFormattingContext | None = None,
) -> list[dict]:
    return calculate_financial_calendar_projection(
        user=user,
        date_from=date_from,
        date_to=date_to,
        account_ids=account_ids,
        events=events,
        formatting_context=formatting_context,
    ).day_forecasts


def sum_event_amounts(events: Iterable[dict]) -> Decimal:
    return sum(
        (Decimal(str(event.get("amountRub") or "0.00")) for event in events),
        Decimal("0.00"),
    )


def mark_sharp_change_events(*, events: list[dict], opening_balance: Decimal) -> None:
    threshold = get_sharp_change_threshold(opening_balance)
    for event in events:
        amount = Decimal(str(event.get("amountRub") or "0.00"))
        event["isSharpChange"] = abs(amount) >= threshold


def build_financial_calendar_cells(
    *,
    year: int,
    month: int,
    day_forecasts: list[dict],
    events: list[dict],
    formatting_context: AppSettingsFormattingContext,
    user,
) -> list[dict]:
    forecasts_by_date = {item["date"]: item for item in day_forecasts}
    events_by_date: dict[str, list[dict]] = {}

    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)

    cells = []
    for iso, forecast in forecasts_by_date.items():
        current_date = date.fromisoformat(iso)
        cells.append(
            {
                "iso": iso,
                "dateLabel": format_app_date(current_date, formatting_context),
                "day": current_date.day,
                "inMonth": current_date.year == year and current_date.month == month,
                "isToday": forecast["isToday"],
                "isSaturday": current_date.weekday() == 5,
                "isSunday": current_date.weekday() == 6,
                "forecastBalanceRub": forecast["forecastBalanceRub"],
                "forecastBalanceLabel": forecast["forecastBalanceLabel"],
                "actualBalanceRub": forecast["actualBalanceRub"],
                "actualBalanceLabel": forecast["actualBalanceLabel"],
                "riskLevel": forecast["riskLevel"],
                "events": events_by_date.get(iso, []),
            }
        )
    return cells


def get_financial_calendar_day(
    *,
    user,
    iso: date,
    account_ids: list[int] | None = None,
    event_types: Iterable[str] | None = None,
    timezone_value: str | None = None,
) -> dict:
    formatting_context = build_app_formatting_context(user, timezone_value=timezone_value)
    resolved_account_ids = get_financial_calendar_account_ids(user, account_ids)
    resolved_event_types = set(event_types or FINANCIAL_CALENDAR_EVENT_TYPES)
    events = get_financial_calendar_events(
        user=user,
        date_from=iso,
        date_to=iso,
        account_ids=resolved_account_ids,
        event_types=resolved_event_types,
        formatting_context=formatting_context,
    )
    projection = calculate_financial_calendar_projection(
        user=user,
        date_from=iso,
        date_to=iso,
        account_ids=resolved_account_ids,
        events=events,
        formatting_context=formatting_context,
    )
    mark_sharp_change_events(
        events=events,
        opening_balance=projection.opening_balance,
    )

    return {
        "iso": iso.isoformat(),
        "dateLabel": format_app_date(iso, formatting_context),
        "dayBalance": projection.day_forecasts[0] if projection.day_forecasts else None,
        "events": events,
    }


def get_financial_calendar_meta(user) -> dict:
    formatting_context = build_app_formatting_context(user)
    accounts = Account.objects.filter(
        user=user,
        is_active=True,
        is_archived=False,
    ).order_by("name")
    opening_balance = accounts.aggregate(total=Sum("balance")).get("total") or Decimal("0.00")

    return {
        "accounts": [
            {
                "id": account.id,
                "title": account.name,
                "subtitle": f"{account.currency} · {mask_account_suffix(account.id)}",
                "color": account.color,
            }
            for account in accounts
        ],
        "eventTypes": [
            {
                "value": FINANCIAL_CALENDAR_EVENT_INCOME,
                "label": "Доход",
                "icon": "arrow-down",
                "color": "#16A34A",
            },
            {
                "value": FINANCIAL_CALENDAR_EVENT_EXPENSE,
                "label": "Расход",
                "icon": "arrow-up",
                "color": "#DC2626",
            },
            {
                "value": FINANCIAL_CALENDAR_EVENT_TRANSFER,
                "label": "Перевод",
                "icon": "arrows-right-left",
                "color": "#64748B",
            },
            {
                "value": FINANCIAL_CALENDAR_EVENT_REMINDER,
                "label": "Напоминание",
                "icon": "bell",
                "color": "#F97316",
            },
        ],
        "timezones": FINANCIAL_CALENDAR_TIMEZONES,
        "defaultTimezone": formatting_context.timezone_name,
        "openingBalanceRub": format_money(opening_balance),
        "openingBalanceLabel": get_calendar_money_label(opening_balance, formatting_context, user),
    }


def build_financial_calendar_export_preview(
    *,
    user,
    year: int,
    month: int,
    account_ids: list[int] | None = None,
    event_types: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timezone_value: str | None = None,
) -> dict:
    export_date_from, export_date_to = resolve_financial_calendar_export_period(
        year=year,
        month=month,
        date_from=date_from,
        date_to=date_to,
    )
    month_data = build_financial_calendar_month(
        user=user,
        year=year,
        month=month,
        account_ids=account_ids,
        event_types=event_types,
        date_from=export_date_from,
        date_to=export_date_to,
        timezone_value=timezone_value,
    )
    rows = build_financial_calendar_export_rows(
        day_forecasts=month_data["dayForecasts"],
        events=month_data["events"],
    )
    return {"rows": rows}


def build_financial_calendar_export_response(
    *,
    user,
    year: int,
    month: int,
    export_format: str | None = None,
    columns: dict | None = None,
    account_ids: list[int] | None = None,
    event_types: Iterable[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timezone_value: str | None = None,
) -> dict:
    normalized_format = normalize_financial_calendar_export_format(export_format)
    if normalized_format not in FINANCIAL_CALENDAR_EXPORT_FORMATS:
        raise ValueError("Формат экспорта должен быть csv, pdf или xlsx.")

    normalized_columns = normalize_financial_calendar_export_columns(columns)
    preview = build_financial_calendar_export_preview(
        user=user,
        year=year,
        month=month,
        account_ids=account_ids,
        event_types=event_types,
        date_from=date_from,
        date_to=date_to,
        timezone_value=timezone_value,
    )
    export_result = build_financial_calendar_export_file(
        rows=preview["rows"],
        export_format=normalized_format,
        columns=normalized_columns,
        year=year,
        month=month,
    )
    return {
        "downloadUrl": build_financial_calendar_download_url(export_result),
        "fileName": export_result.filename,
    }


def build_financial_calendar_export_rows(*, day_forecasts: list[dict], events: list[dict]) -> list[dict]:
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)

    rows = []
    for forecast in day_forecasts:
        day_events = events_by_date.get(forecast["date"], [])
        rows.append(
            {
                "date": forecast.get("dateLabel") or forecast["date"],
                "iso": forecast["date"],
                "actualRub": forecast["actualBalanceRub"] or "0.00",
                "forecastRub": forecast["forecastBalanceRub"],
                "eventsSummary": build_events_summary(day_events),
                "riskLevel": forecast["riskLevel"],
                "riskLabel": get_risk_label(forecast["riskLevel"]),
            }
        )
    return rows


def resolve_financial_calendar_export_period(
    *,
    year: int,
    month: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[date, date]:
    month_first_day = date(year, month, 1)
    _, last_day_number = calendar.monthrange(year, month)
    month_last_day = date(year, month, last_day_number)

    resolved_date_from = date_from or month_first_day
    resolved_date_to = date_to or month_last_day

    if resolved_date_from > resolved_date_to:
        raise ValueError("dateFrom не может быть позже dateTo.")

    if (resolved_date_to - resolved_date_from).days > MAX_FINANCIAL_CALENDAR_RANGE_DAYS:
        raise ValueError(
            f"Период экспорта календаря не должен превышать {MAX_FINANCIAL_CALENDAR_RANGE_DAYS} дней."
        )

    return resolved_date_from, resolved_date_to


def build_events_summary(events: list[dict]) -> str:
    if not events:
        return "—"

    titles = [str(event.get("title") or "Событие") for event in events]
    if len(titles) <= 3:
        return ", ".join(titles)

    return f"{', '.join(titles[:3])}, +{len(titles) - 3} ещё"


def get_risk_label(risk_level: str) -> str:
    if risk_level == FINANCIAL_CALENDAR_RISK_RISK:
        return "Риск"
    if risk_level == FINANCIAL_CALENDAR_RISK_CAUTION:
        return "Внимание"
    return "Безопасно"


def find_cash_gap_range(day_forecasts: list[dict]) -> dict | None:
    gap_start = None
    gap_end = None

    for forecast in day_forecasts:
        if Decimal(str(forecast["forecastBalanceRub"])) < 0:
            if gap_start is None:
                gap_start = forecast["date"]
            gap_end = forecast["date"]
        elif gap_start is not None:
            break

    if gap_start is None:
        return None

    return {
        "startIso": gap_start,
        "endIso": gap_end,
    }


def get_calendar_risk_level(
    *,
    opening_balance: Decimal,
    forecast_balance: Decimal,
    total_delta: Decimal,
) -> str:
    if forecast_balance < 0:
        return FINANCIAL_CALENDAR_RISK_RISK

    if opening_balance > 0:
        low_balance_threshold = opening_balance * Decimal("0.10")
        if forecast_balance <= low_balance_threshold or abs(total_delta) >= get_sharp_change_threshold(opening_balance):
            return FINANCIAL_CALENDAR_RISK_CAUTION

    return FINANCIAL_CALENDAR_RISK_SAFE


def get_sharp_change_threshold(opening_balance: Decimal) -> Decimal:
    base = abs(opening_balance) * Decimal("0.25")
    return max(base, Decimal("10000.00"))


def get_signed_amount(transaction_type: str, amount: Decimal) -> Decimal:
    if transaction_type == TransactionType.INCOME:
        return amount
    return -amount


def format_money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(Decimal("0.01")))


def mask_account_suffix(account_id: int) -> str:
    return f"•••{str(account_id).zfill(4)[-4:]}"
