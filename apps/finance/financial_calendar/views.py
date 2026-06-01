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
from apps.finance.financial_calendar.services import (
    FINANCIAL_CALENDAR_EVENT_TYPES,
    build_financial_calendar_export_preview,
    build_financial_calendar_converter,
    build_financial_calendar_export_response,
    build_financial_calendar_month,
    get_financial_calendar_account_ids,
    get_financial_calendar_day,
    get_financial_calendar_events,
    get_financial_calendar_meta,
)
from apps.users.app_settings.formatting import build_app_formatting_context
from apps.finance.financial_calendar.serializers import (
    FinancialCalendarDayResponseSerializer,
    FinancialCalendarEventsResponseSerializer,
    FinancialCalendarExportPreviewResponseSerializer,
    FinancialCalendarExportRequestSerializer,
    FinancialCalendarExportResponseSerializer,
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


def get_financial_calendar_display_currency_query_param(query_params) -> str | None:
    return (
        query_params.get("currency")
        or query_params.get("currencyCode")
        or query_params.get("currency_code")
        or None
    )


def get_financial_calendar_year_month(query_params, user) -> tuple[int, int]:
    from django.utils import timezone

    app_timezone = build_app_formatting_context(user).timezone
    today = timezone.localdate(timezone=app_timezone)
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
    timezone_value = query_params.get("timezone") or None
    display_currency = get_financial_calendar_display_currency_query_param(query_params)

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
        "display_currency": display_currency,
    }


def get_bool_export_column_query_param(query_params, *names: str) -> bool | None:
    for name in names:
        raw_value = query_params.get(name)
        if raw_value in (None, ""):
            continue
        normalized = str(raw_value).strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        raise ValidationError({name: ["Значение должно быть true или false."]})

    return None


def get_financial_calendar_export_columns_from_query(query_params) -> dict | None:
    aliases = {
        "actual": ("actual", "columnsActual", "columns[actual]"),
        "balance": ("balance", "columnsBalance", "columns[balance]"),
        "events": ("events", "columnsEvents", "columns[events]"),
        "risks": ("risks", "columnsRisks", "columns[risks]"),
    }
    columns: dict[str, bool] = {}

    for key, names in aliases.items():
        value = get_bool_export_column_query_param(query_params, *names)
        if value is not None:
            columns[key] = value

    return columns or None


def get_financial_calendar_export_params_from_query(request) -> dict:
    year, month = get_financial_calendar_year_month(request.query_params, request.user)
    common_params = get_financial_calendar_common_params(request)
    return {
        "year": year,
        "month": month,
        "date_from": get_date_query_param(request.query_params, "dateFrom"),
        "date_to": get_date_query_param(request.query_params, "dateTo"),
        "export_format": request.query_params.get("format") or None,
        "columns": get_financial_calendar_export_columns_from_query(request.query_params),
        **common_params,
    }


def get_financial_calendar_export_params_from_body(request) -> dict:
    serializer = FinancialCalendarExportRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    return {
        "year": data["year"],
        "month": data["month"],
        "date_from": data.get("dateFrom"),
        "date_to": data.get("dateTo"),
        "export_format": data.get("format"),
        "columns": data.get("columns"),
        "account_ids": data.get("accountIds"),
        "event_types": data.get("eventTypes"),
        "timezone_value": data.get("timezone"),
        "display_currency": data.get("currency"),
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
            "дельты, фактический баланс для прошлых дней, прогнозный баланс "
            "и первый найденный кассовый разрыв. "
            "Месяц в API передаётся в формате 1-12. Суммы приводятся к валюте отображения из параметра currency или из настроек пользователя."
        ),
        parameters=[
            OpenApiParameter("year", OpenApiTypes.INT, description="Год календаря, например 2026."),
            OpenApiParameter("month", OpenApiTypes.INT, description="Месяц календаря от 1 до 12."),
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов. Можно передавать повторяющимся параметром или через запятую."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий: income, expense, transfer, reminder."),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Нижняя граница периода, YYYY-MM-DD. Опционально."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Верхняя граница периода, YYYY-MM-DD. Опционально."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="IANA-часовой пояс, например Asia/Krasnoyarsk. Если параметр не передан, используется настройка пользователя."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм, например RUB, USD или EUR."),
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
                    "todayLabel": "22.05.2026",
                    "openingBalanceRub": "227800.00",
                    "openingBalance": {"amount": 227800.0, "currency": "RUB"},
                    "openingBalanceLabel": "227 800,00 ₽",
                    "currency": "RUB",
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
        year, month = get_financial_calendar_year_month(request.query_params, request.user)
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
            OpenApiParameter("timezone", OpenApiTypes.STR, description="IANA-часовой пояс, например Asia/Krasnoyarsk. Если параметр не передан, используется настройка пользователя."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм, например RUB, USD или EUR."),
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
            converter = build_financial_calendar_converter(
                user=request.user,
                display_currency=common_params["display_currency"],
            )
            events = get_financial_calendar_events(
                user=request.user,
                date_from=date_from,
                date_to=date_to,
                account_ids=account_ids,
                event_types=set(common_params["event_types"] or FINANCIAL_CALENDAR_EVENT_TYPES),
                formatting_context=build_app_formatting_context(
                    request.user,
                    timezone_value=common_params["timezone_value"],
                ),
                converter=converter,
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response({
            "items": events,
            "currency": converter.display_currency,
            "currencyContext": converter.context_payload(),
        })


class FinancialCalendarDayView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить детали дня финансового календаря",
        description="Возвращает баланс дня и события за конкретную дату.",
        parameters=[
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="IANA-часовой пояс, например Asia/Krasnoyarsk. Если параметр не передан, используется настройка пользователя."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм, например RUB, USD или EUR."),
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
                timezone_value=common_params["timezone_value"],
                display_currency=common_params["display_currency"],
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
            "часовые пояса из настроек приложения и баланс активных счетов для стартового состояния формы."
        ),
        parameters=[
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм, например RUB, USD или EUR."),
        ],
        responses={200: FinancialCalendarMetaResponseSerializer},
    )
    def get(self, request):
        return Response(
            get_financial_calendar_meta(
                request.user,
                display_currency=get_financial_calendar_display_currency_query_param(request.query_params),
            )
        )



class FinancialCalendarExportPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Получить предварительный просмотр экспорта финансового календаря",
        description=(
            "Возвращает строки предварительного просмотра для окна экспорта финансового календаря. "
            "По умолчанию период ограничивается выбранным календарным месяцем. "
            "Если переданы dateFrom и dateTo, используется указанный диапазон."
        ),
        parameters=[
            OpenApiParameter("year", OpenApiTypes.INT, required=True, description="Год календаря, например 2026."),
            OpenApiParameter("month", OpenApiTypes.INT, required=True, description="Месяц календаря от 1 до 12."),
            OpenApiParameter("accountIds", OpenApiTypes.INT, many=True, description="ID счетов. Можно передавать повторяющимся параметром или через запятую."),
            OpenApiParameter("eventTypes", OpenApiTypes.STR, many=True, description="Типы событий: income, expense, transfer, reminder."),
            OpenApiParameter("dateFrom", OpenApiTypes.DATE, description="Нижняя граница периода, YYYY-MM-DD."),
            OpenApiParameter("dateTo", OpenApiTypes.DATE, description="Верхняя граница периода, YYYY-MM-DD."),
            OpenApiParameter("timezone", OpenApiTypes.STR, description="IANA-часовой пояс, например Asia/Krasnoyarsk."),
            OpenApiParameter("currency", OpenApiTypes.STR, description="Валюта отображения сумм, например RUB, USD или EUR."),
        ],
        responses={
            200: FinancialCalendarExportPreviewResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры периода или фильтров."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Предварительный просмотр экспорта",
                value={
                    "rows": [
                        {
                            "date": "15.05.2026",
                            "iso": "2026-05-15",
                            "actualRub": "349750.00",
                            "forecastRub": "291500.00",
                            "eventsSummary": "Подработка, Перекрёсток, Топливо",
                            "riskLevel": "safe",
                            "riskLabel": "Безопасно",
                        }
                    ]
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        params = get_financial_calendar_export_params_from_query(request)

        try:
            data = build_financial_calendar_export_preview(
                user=request.user,
                year=params["year"],
                month=params["month"],
                account_ids=params["account_ids"],
                event_types=params["event_types"],
                date_from=params["date_from"],
                date_to=params["date_to"],
                timezone_value=params["timezone_value"],
                display_currency=params["display_currency"],
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response(data)


class FinancialCalendarExportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_CALENDAR_TAG],
        summary="Экспортировать финансовый календарь",
        description=(
            "Формирует файл финансового календаря в формате CSV, PDF или XLSX и возвращает "
            "имя файла вместе с data URL. Такой вариант не требует отдельного файлового хранилища "
            "и подходит для MVP-интеграции с кнопкой скачивания на фронте."
        ),
        request=FinancialCalendarExportRequestSerializer,
        responses={
            200: FinancialCalendarExportResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры экспорта."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Запрос экспорта XLSX",
                value={
                    "year": 2026,
                    "month": 5,
                    "format": "xlsx",
                    "columns": {
                        "actual": True,
                        "balance": True,
                        "events": True,
                        "risks": True,
                    },
                    "accountIds": [1, 2],
                    "eventTypes": ["income", "expense", "reminder"],
                    "timezone": "Asia/Krasnoyarsk",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Ответ экспорта",
                value={
                    "downloadUrl": "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,...",
                    "fileName": "financial_calendar_2026_05_20260524_120000.xlsx",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        params = get_financial_calendar_export_params_from_body(request)

        try:
            data = build_financial_calendar_export_response(
                user=request.user,
                year=params["year"],
                month=params["month"],
                export_format=params["export_format"],
                columns=params["columns"],
                account_ids=params["account_ids"],
                event_types=params["event_types"],
                date_from=params["date_from"],
                date_to=params["date_to"],
                timezone_value=params["timezone_value"],
                display_currency=params["display_currency"],
            )
        except ValueError as exc:
            handle_financial_calendar_value_error(exc)

        return Response(data)
