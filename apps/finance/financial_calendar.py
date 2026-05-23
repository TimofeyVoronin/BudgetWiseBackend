from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum
from django.utils import timezone

from apps.finance.models import (
    Account,
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
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

DEFAULT_FINANCIAL_CALENDAR_TIMEZONE = "UTC+7"
FINANCIAL_CALENDAR_TIMEZONES = [
    {
        "value": "UTC+0",
        "label": "UTC+0",
        "offsetHours": 0,
    },
    {
        "value": "UTC+3",
        "label": "UTC+3 Москва",
        "offsetHours": 3,
    },
    {
        "value": "UTC+7",
        "label": "UTC+7 Красноярск",
        "offsetHours": 7,
    },
]

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
    timezone_value: str = DEFAULT_FINANCIAL_CALENDAR_TIMEZONE,
) -> dict:
    query = build_financial_calendar_query(
        user=user,
        year=year,
        month=month,
        account_ids=account_ids,
        event_types=event_types,
        date_from=date_from,
        date_to=date_to,
        timezone_value=timezone_value,
    )

    events = get_financial_calendar_events(
        user=user,
        date_from=query.grid_date_from,
        date_to=query.grid_date_to,
        account_ids=query.account_ids,
        event_types=query.event_types,
    )
    day_forecasts = calculate_financial_calendar_day_forecasts(
        user=user,
        date_from=query.grid_date_from,
        date_to=query.grid_date_to,
        account_ids=query.account_ids,
        events=events,
    )
    cells = build_financial_calendar_cells(
        year=year,
        month=month,
        day_forecasts=day_forecasts,
        events=events,
    )

    return {
        "year": year,
        "month": month,
        "todayIso": timezone.localdate().isoformat(),
        "openingBalanceRub": format_money(get_accounts_opening_balance(user, query.account_ids)),
        "cells": cells,
        "events": events,
        "dayForecasts": day_forecasts,
        "cashGap": find_cash_gap_range(day_forecasts),
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
    timezone_value: str = DEFAULT_FINANCIAL_CALENDAR_TIMEZONE,
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

    if timezone_value not in {item["value"] for item in FINANCIAL_CALENDAR_TIMEZONES}:
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
        timezone_value=timezone_value,
    )


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
    if not account_ids:
        return Decimal("0.00")

    value = (
        Account.objects
        .filter(user=user, id__in=account_ids, is_active=True, is_archived=False)
        .aggregate(total=Sum("balance"))
        .get("total")
    )
    return value or Decimal("0.00")


def get_financial_calendar_events(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: list[int],
    event_types: set[str] | None = None,
) -> list[dict]:
    if not account_ids:
        return []

    event_types = event_types or FINANCIAL_CALENDAR_EVENT_TYPES
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
            events.append(transaction_to_calendar_event(transaction))

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
            events.append(planned_to_calendar_event(planned))

    events.sort(key=lambda item: (item["date"], item["status"], item["id"]))
    return events


def transaction_to_calendar_event(transaction: Transaction) -> dict:
    signed_amount = get_signed_amount(transaction.type, transaction.amount)
    title = transaction.description.strip() if transaction.description else transaction.category.name

    return {
        "id": f"tx-{transaction.id}",
        "sourceId": transaction.id,
        "sourceType": "transaction",
        "date": transaction.operation_date.isoformat(),
        "type": transaction.type,
        "title": title,
        "subtitle": transaction.category.name,
        "amountRub": format_money(signed_amount),
        "accountId": transaction.account_id,
        "accountName": transaction.account.name,
        "status": FINANCIAL_CALENDAR_STATUS_CONFIRMED,
        "isSharpChange": False,
    }


def planned_to_calendar_event(planned: PlannedTransaction) -> dict:
    signed_amount = get_signed_amount(planned.type, planned.amount)

    return {
        "id": f"planned-{planned.id}",
        "sourceId": planned.id,
        "sourceType": "planned_transaction",
        "date": planned.planned_date.isoformat(),
        "type": planned.type,
        "title": planned.name,
        "subtitle": planned.category.name,
        "amountRub": format_money(signed_amount),
        "accountId": planned.account_id,
        "accountName": planned.account.name,
        "status": FINANCIAL_CALENDAR_STATUS_PENDING,
        "isSharpChange": False,
    }


def calculate_financial_calendar_day_forecasts(
    *,
    user,
    date_from: date,
    date_to: date,
    account_ids: list[int],
    events: list[dict],
) -> list[dict]:
    opening_balance = get_accounts_opening_balance(user, account_ids)
    events_by_date: dict[str, list[dict]] = {}

    for event in events:
        events_by_date.setdefault(event["date"], []).append(event)

    today = timezone.localdate()
    current_date = date_from
    forecast_balance = opening_balance
    rows: list[dict] = []

    while current_date <= date_to:
        iso = current_date.isoformat()
        day_events = events_by_date.get(iso, [])
        total_delta = sum(
            (Decimal(str(event.get("amountRub") or "0.00")) for event in day_events),
            Decimal("0.00"),
        )
        forecast_balance += total_delta

        is_past = current_date < today
        is_today = current_date == today
        actual_balance = forecast_balance if current_date <= today else None

        rows.append(
            {
                "date": iso,
                "actualBalanceRub": format_money(actual_balance) if actual_balance is not None else None,
                "forecastBalanceRub": format_money(forecast_balance),
                "totalDelta": format_money(total_delta),
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

    return rows


def build_financial_calendar_cells(
    *,
    year: int,
    month: int,
    day_forecasts: list[dict],
    events: list[dict],
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
                "day": current_date.day,
                "inMonth": current_date.year == year and current_date.month == month,
                "isToday": forecast["isToday"],
                "isSaturday": current_date.weekday() == 5,
                "isSunday": current_date.weekday() == 6,
                "forecastBalanceRub": forecast["forecastBalanceRub"],
                "actualBalanceRub": forecast["actualBalanceRub"],
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
) -> dict:
    resolved_account_ids = get_financial_calendar_account_ids(user, account_ids)
    resolved_event_types = set(event_types or FINANCIAL_CALENDAR_EVENT_TYPES)
    events = get_financial_calendar_events(
        user=user,
        date_from=iso,
        date_to=iso,
        account_ids=resolved_account_ids,
        event_types=resolved_event_types,
    )
    day_forecasts = calculate_financial_calendar_day_forecasts(
        user=user,
        date_from=iso,
        date_to=iso,
        account_ids=resolved_account_ids,
        events=events,
    )

    return {
        "iso": iso.isoformat(),
        "dayBalance": day_forecasts[0] if day_forecasts else None,
        "events": events,
    }


def get_financial_calendar_meta(user) -> dict:
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
        "defaultTimezone": DEFAULT_FINANCIAL_CALENDAR_TIMEZONE,
        "openingBalanceRub": format_money(opening_balance),
    }


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
        sharp_change_threshold = opening_balance * Decimal("0.25")
        if forecast_balance <= low_balance_threshold or abs(total_delta) >= sharp_change_threshold:
            return FINANCIAL_CALENDAR_RISK_CAUTION

    return FINANCIAL_CALENDAR_RISK_SAFE


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
