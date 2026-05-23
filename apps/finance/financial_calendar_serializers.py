from __future__ import annotations

from rest_framework import serializers


FINANCIAL_CALENDAR_EVENT_TYPE_CHOICES = [
    ("income", "Доход"),
    ("expense", "Расход"),
    ("transfer", "Перевод"),
    ("reminder", "Напоминание"),
]
FINANCIAL_CALENDAR_EVENT_STATUS_CHOICES = [
    ("confirmed", "Факт"),
    ("pending", "План"),
]
FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES = [
    ("safe", "Безопасно"),
    ("caution", "Внимание"),
    ("risk", "Риск кассового разрыва"),
]


class FinancialCalendarEventSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Идентификатор события календаря с префиксом источника.")
    sourceId = serializers.IntegerField(help_text="ID исходной операции или плановой операции.")
    sourceType = serializers.CharField(help_text="Источник события: transaction или planned_transaction.")
    date = serializers.DateField(help_text="Дата события в формате YYYY-MM-DD.")
    type = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_TYPE_CHOICES, help_text="Тип события календаря.")
    title = serializers.CharField(help_text="Заголовок события для ячейки и панели дня.")
    subtitle = serializers.CharField(help_text="Подзаголовок: категория, описание или служебная подпись.")
    amountRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Сумма в рублях. Доход положительный, расход отрицательный.")
    accountId = serializers.IntegerField(help_text="ID счёта события.")
    accountName = serializers.CharField(help_text="Название счёта события.")
    status = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_STATUS_CHOICES, help_text="Статус события: confirmed для факта, pending для плана.")
    isSharpChange = serializers.BooleanField(help_text="Признак резкого изменения баланса для подсветки риска.")


class FinancialCalendarDayForecastSerializer(serializers.Serializer):
    date = serializers.DateField(help_text="Дата прогноза в формате YYYY-MM-DD.")
    actualBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Фактический баланс на конец дня. Для будущих дней null.")
    forecastBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Прогнозный баланс на конец дня.")
    totalDelta = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Суммарное изменение за день.")
    hasEvents = serializers.BooleanField(help_text="Есть ли события в этот день.")
    riskLevel = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES, help_text="Уровень риска по остатку дня.")
    isToday = serializers.BooleanField(help_text="Признак сегодняшнего дня.")
    isPast = serializers.BooleanField(help_text="Признак прошедшего дня.")


class FinancialCalendarCashGapRangeSerializer(serializers.Serializer):
    startIso = serializers.DateField(help_text="Дата начала периода кассового разрыва.")
    endIso = serializers.DateField(help_text="Дата окончания периода кассового разрыва.")


class FinancialCalendarMonthCellSerializer(serializers.Serializer):
    iso = serializers.DateField(help_text="Дата ячейки в формате YYYY-MM-DD.")
    day = serializers.IntegerField(help_text="Число месяца.")
    inMonth = serializers.BooleanField(help_text="Ячейка относится к выбранному месяцу.")
    isToday = serializers.BooleanField(help_text="Признак сегодняшнего дня.")
    isSaturday = serializers.BooleanField(help_text="Признак субботы.")
    isSunday = serializers.BooleanField(help_text="Признак воскресенья.")
    forecastBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Прогнозный баланс на конец дня.")
    actualBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Фактический баланс на конец дня или null для будущих дней.")
    riskLevel = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES, help_text="Уровень риска ячейки.")
    events = FinancialCalendarEventSerializer(many=True, help_text="События дня.")


class FinancialCalendarMonthResponseSerializer(serializers.Serializer):
    year = serializers.IntegerField(help_text="Год календаря.")
    month = serializers.IntegerField(help_text="Месяц календаря, 1-12.")
    todayIso = serializers.DateField(help_text="Сегодняшняя дата по часовому поясу backend.")
    openingBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Остаток активных счетов на начало расчёта.")
    cells = FinancialCalendarMonthCellSerializer(many=True, help_text="Расширенная сетка месяца с соседними днями.")
    events = FinancialCalendarEventSerializer(many=True, help_text="Все события в диапазоне сетки.")
    dayForecasts = FinancialCalendarDayForecastSerializer(many=True, help_text="Прогнозы баланса по дням.")
    cashGap = FinancialCalendarCashGapRangeSerializer(allow_null=True, help_text="Первый найденный диапазон кассового разрыва.")


class FinancialCalendarEventsResponseSerializer(serializers.Serializer):
    items = FinancialCalendarEventSerializer(many=True, help_text="Список событий календаря.")


class FinancialCalendarDayResponseSerializer(serializers.Serializer):
    iso = serializers.DateField(help_text="Дата дня в формате YYYY-MM-DD.")
    dayBalance = FinancialCalendarDayForecastSerializer(allow_null=True, help_text="Баланс и прогноз по выбранному дню.")
    events = FinancialCalendarEventSerializer(many=True, help_text="События выбранного дня.")


class FinancialCalendarAccountOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="ID счёта.")
    title = serializers.CharField(help_text="Название счёта.")
    subtitle = serializers.CharField(help_text="Подпись счёта для фильтра.")
    color = serializers.CharField(help_text="HEX-цвет счёта.")


class FinancialCalendarEventTypeOptionSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_TYPE_CHOICES, help_text="Тип события.")
    label = serializers.CharField(help_text="Подпись типа события.")
    icon = serializers.CharField(help_text="Код иконки.")
    color = serializers.CharField(help_text="HEX-цвет типа события.")


class FinancialCalendarTimezoneOptionSerializer(serializers.Serializer):
    value = serializers.CharField(help_text="Метка часового пояса.")
    label = serializers.CharField(help_text="Название часового пояса для интерфейса.")
    offsetHours = serializers.IntegerField(help_text="Смещение от UTC в часах.")


class FinancialCalendarMetaResponseSerializer(serializers.Serializer):
    accounts = FinancialCalendarAccountOptionSerializer(many=True, help_text="Активные счета пользователя для фильтров.")
    eventTypes = FinancialCalendarEventTypeOptionSerializer(many=True, help_text="Типы событий календаря.")
    timezones = FinancialCalendarTimezoneOptionSerializer(many=True, help_text="Доступные часовые пояса.")
    defaultTimezone = serializers.CharField(help_text="Часовой пояс по умолчанию.")
    openingBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Текущий остаток активных счетов пользователя.")
