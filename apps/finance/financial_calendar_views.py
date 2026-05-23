from __future__ import annotations

from datetime import date

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.validation import get_date_query_param, get_int_query_param
from apps.finance.financial_calendar import (
    DEFAULT_FINANCIAL_CALENDAR_TIMEZONE,
    FINANCIAL_CALENDAR_EVENT_TYPES,
    build_financial_calendar_month,
    get_financial_calendar_account_ids,
    get_financial_calendar_day,
    get_financial_calendar_events,
    get_financial_calendar_meta,
    resolve_month_grid,
)
from apps.finance.financial_calendar_serializers import (
    FinancialCalendarDayResponseSerializer,
    FinancialCalendarEventsResponseSerializer,
    FinancialCalendarMetaResponseSerializer,
    FinancialCalendarMonthResponseSerializer,
)


FINANCIAL_CALENDAR_TAG = "finance-calendar"


def get_multi_query_int_values(query_params, *names: str) -> list[int] | None:
    raw_values: list[str] = []

    for name in names:
        raw_values.extend(query_params.getlist(name))

    if not raw_values:
        return None

    values: list[int] = []
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        for chunk in str(raw_value).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                values.append(int(chunk))
            except ValueError as exc:
                raise ValidationError(
                    {names[0]: ["ID счёта должен быть целым числом."]}
                ) from exc

    return values or None


def get_multi_query_str_values(query_params, *names: str) -> list[str] | None:
    raw_values: list[str] = []

    for name in names:
        raw_values.extend(query_params.getlist(name))

    if not raw_values:
        return None

    values: list[str] = []
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        for chunk in str(raw_value).split(","):
            chunk = chunk.strip()
            if chunk:
                values.append(chunk)

    return values or None


def get_financial_calendar_year_month(query_params) -> tuple[int, int]:
    today = date.today()
    year = get_int_query_param(query_params, "year") or today.year
    month = get_int_query_param(query_params, "month") or today.month

    if year < 2000 or year > 2100:
        raise ValidationError({"year": ["Год должен быть от 2000 до 2100."]})

    if month < 1 or month > 12:
        raise ValidationError({"month": ["Месяц должен быть от 1 до 12."]})

    return year, month


def get_financial_calendar_common_params(request) -> dict:
    query_params = request.query_params
    account_ids = get_multi_query_int_values(query_params, "accountIds", "account_ids")
    event_types = get_multi_query_str_values(query_params, "eventTypes", "event_types")
    timezone_value = query_params.get("timezone") or DEFAULT_FINANCIAL_CALENDAR_TIMEZONE

    if event_types:
        invalid_values = set(event_types) - FINANCIAL_CALENDAR_EVENT_TYPES
        if invalid_values:
            allowed_values = ", ".join(sorted(FINANCIAL_CALENDAR_EVENT_TYPES))
            raise ValidationError(
                {
                    "eventTypes": [
                        f"Недопустимые типы событий. Допустимые значения: {allowed_values}."
                    ]
                }
            )

    return {
        "account_ids": account_ids,
        "event_types": event_types,
        "timezone_value": timezone_value,
    }


def handle_financial_calendar_value_error(exc: ValueError) -> None:
    message = str(exc) or "Некорректные параметры финансового календаря."
    raise ValidationError({"nonFieldErrors": [message]}) from exc


class FinancialCalendarMonthView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить финансовый календарь на месяц",
        description=(
            "Возвращает расширенную месячную сетку финансового календаря: "
            "ячейки дней, фактические операции, плановые операции, дневные "
            "дельты, прогнозный баланс и первый найденный кассовый разрыв. "
            "Месяц в API передаётся в формате 1-12. Конвертация валют не выполняется."
        ),
        parameters=[
            OpenApiParameter("year", OpenApiTypes.INT, description="Год календаря, например 2026."),
            OpenApiParameter("month", OpenApiTypes.INT, description="Месяц календаря от 1 до 12."),
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов. Можно передавать повторяющимся параметром или через запятую."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий: income, expense, transfer, reminder."),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Нижняя граница периода, YYYY-MM-DD. Опционально."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Верхняя граница периода, YYYY-MM-DD. Опционально."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="Метка часового пояса, например UTC+7."),
        ],
        responses={
            200: FinancialCalendarMonthResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры периода или фильтров."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Финансовый календарь на месяц",
                value={
                    "year": 2026,
                    "month": 5,
                    "todayIso": "2026-05-22",
                    "openingBalanceRub": "227800.00",
                    "cells": [],
                    "events": [],
                    "dayForecasts": [],
                    "cashGap": None,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        year, month = get_financial_calendar_year_month(request.query_params)
        common_params = get_financial_calendar_common_params(request)
        date_from = get_date_query_param(request.query_params, "dateFrom")
        date_to = get_date_query_param(request.query_params, "dateTo")

        try:
            data = build_financial_calendar_month(
                user=request.user,
                year=year,
                month=month,
                date_from=date_from,
                date_to=date_to,
                **common_params,
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response(data)


class FinancialCalendarEventsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить события финансового календаря",
        description=(
            "Возвращает события календаря в указанном диапазоне: фактические "
            "операции и плановые операции, участвующие в прогнозе."
        ),
        parameters=[
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, required=True, description="Дата начала, YYYY-MM-DD."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, required=True, description="Дата окончания, YYYY-MM-DD."),
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий: income, expense, transfer, reminder."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="Метка часового пояса."),
        ],
        responses={200: FinancialCalendarEventsResponseSerializer},
    )
    def get(self, request):
        date_from = get_date_query_param(request.query_params, "dateFrom")
        date_to = get_date_query_param(request.query_params, "dateTo")

        if date_from is None or date_to is None:
            raise ValidationError({"dateFrom": ["Укажите dateFrom и dateTo."]})

        if date_from > date_to:
            raise ValidationError({"dateFrom": ["dateFrom не может быть позже dateTo."]})

        common_params = get_financial_calendar_common_params(request)

        try:
            account_ids = get_financial_calendar_account_ids(request.user, common_params["account_ids"])
            events = get_financial_calendar_events(
                user=request.user,
                date_from=date_from,
                date_to=date_to,
                account_ids=account_ids,
                event_types=set(common_params["event_types"] or FINANCIAL_CALENDAR_EVENT_TYPES),
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response({"items": events})


class FinancialCalendarDayView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить детали дня финансового календаря",
        description="Возвращает баланс дня и события за конкретную дату.",
        parameters=[
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="Метка часового пояса."),
        ],
        responses={200: FinancialCalendarDayResponseSerializer},
    )
    def get(self, request, iso: str):
        try:
            parsed_date = date.fromisoformat(iso)
        except ValueError as exc:
            raise ValidationError({"iso": ["Дата должна быть в формате YYYY-MM-DD."]}) from exc

        common_params = get_financial_calendar_common_params(request)

        try:
            data = get_financial_calendar_day(
                user=request.user,
                iso=parsed_date,
                account_ids=common_params["account_ids"],
                event_types=common_params["event_types"],
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response(data)


class FinancialCalendarMetaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить справочники финансового календаря",
        description=(
            "Возвращает активные счета пользователя, типы событий, доступные "
            "часовые пояса и баланс активных счетов для стартового состояния формы."
        ),
        responses={200: FinancialCalendarMetaResponseSerializer},
    )
    def get(self, request):
        return Response(get_financial_calendar_meta(request.user))
