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
    dateLabel = serializers.CharField(required=False, help_text="Дата события в пользовательском формате из настроек приложения.")
    type = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_TYPE_CHOICES, help_text="Тип события календаря.")
    title = serializers.CharField(help_text="Заголовок события для ячейки и панели дня.")
    subtitle = serializers.CharField(help_text="Подзаголовок: категория, описание или служебная подпись.")
    amountRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Сумма в рублях. Доход положительный, расход отрицательный.")
    amountLabel = serializers.CharField(required=False, allow_null=True, help_text="Сумма в пользовательском формате числа с символом валюты.")
    accountId = serializers.IntegerField(help_text="ID счёта события.")
    accountName = serializers.CharField(help_text="Название счёта события.")
    status = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_STATUS_CHOICES, help_text="Статус события: confirmed для факта, pending для плана.")
    isSharpChange = serializers.BooleanField(help_text="Признак резкого изменения баланса для подсветки риска.")


class FinancialCalendarDayForecastSerializer(serializers.Serializer):
    date = serializers.DateField(help_text="Дата прогноза в формате YYYY-MM-DD.")
    dateLabel = serializers.CharField(required=False, help_text="Дата прогноза в пользовательском формате из настроек приложения.")
    actualBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Фактический баланс на конец дня. Для будущих дней null.")
    actualBalanceLabel = serializers.CharField(required=False, allow_null=True, help_text="Фактический баланс в пользовательском формате числа.")
    forecastBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Прогнозный баланс на конец дня с учётом фактических и плановых событий.")
    forecastBalanceLabel = serializers.CharField(required=False, help_text="Прогнозный баланс в пользовательском формате числа.")
    totalDelta = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Суммарное изменение за день по фактическим и плановым событиям.")
    totalDeltaLabel = serializers.CharField(required=False, help_text="Изменение за день в пользовательском формате числа.")
    hasEvents = serializers.BooleanField(help_text="Есть ли события в этот день.")
    riskLevel = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES, help_text="Уровень риска по прогнозному остатку дня: safe, caution или risk.")
    isToday = serializers.BooleanField(help_text="Признак сегодняшнего дня.")
    isPast = serializers.BooleanField(help_text="Признак прошедшего дня.")


class FinancialCalendarCashGapRangeSerializer(serializers.Serializer):
    startIso = serializers.DateField(help_text="Дата начала периода кассового разрыва.")
    endIso = serializers.DateField(help_text="Дата окончания периода кассового разрыва.")


class FinancialCalendarMonthCellSerializer(serializers.Serializer):
    iso = serializers.DateField(help_text="Дата ячейки в формате YYYY-MM-DD.")
    dateLabel = serializers.CharField(required=False, help_text="Дата ячейки в пользовательском формате из настроек приложения.")
    day = serializers.IntegerField(help_text="Число месяца.")
    inMonth = serializers.BooleanField(help_text="Ячейка относится к выбранному месяцу.")
    isToday = serializers.BooleanField(help_text="Признак сегодняшнего дня.")
    isSaturday = serializers.BooleanField(help_text="Признак субботы.")
    isSunday = serializers.BooleanField(help_text="Признак воскресенья.")
    forecastBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Прогнозный баланс на конец дня с учётом фактических и плановых событий.")
    forecastBalanceLabel = serializers.CharField(required=False, help_text="Прогнозный баланс в пользовательском формате числа.")
    actualBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, help_text="Фактический баланс на конец дня или null для будущих дней.")
    actualBalanceLabel = serializers.CharField(required=False, allow_null=True, help_text="Фактический баланс в пользовательском формате числа.")
    riskLevel = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES, help_text="Уровень риска ячейки.")
    events = FinancialCalendarEventSerializer(many=True, help_text="События дня.")


class FinancialCalendarMonthResponseSerializer(serializers.Serializer):
    year = serializers.IntegerField(help_text="Год календаря.")
    month = serializers.IntegerField(help_text="Месяц календаря, 1-12.")
    todayIso = serializers.DateField(help_text="Сегодняшняя дата по часовому поясу пользователя.")
    todayLabel = serializers.CharField(required=False, help_text="Сегодняшняя дата в пользовательском формате из настроек приложения.")
    openingBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Расчётный остаток активных счетов на начало диапазона календаря.")
    openingBalanceLabel = serializers.CharField(required=False, help_text="Остаток на начало диапазона в пользовательском формате числа.")
    cells = FinancialCalendarMonthCellSerializer(many=True, help_text="Расширенная сетка месяца с соседними днями.")
    events = FinancialCalendarEventSerializer(many=True, help_text="Все события в диапазоне сетки.")
    dayForecasts = FinancialCalendarDayForecastSerializer(many=True, help_text="Прогнозы баланса по дням.")
    cashGap = FinancialCalendarCashGapRangeSerializer(allow_null=True, help_text="Первый найденный диапазон кассового разрыва.")


class FinancialCalendarEventsResponseSerializer(serializers.Serializer):
    items = FinancialCalendarEventSerializer(many=True, help_text="Список событий календаря.")


class FinancialCalendarDayResponseSerializer(serializers.Serializer):
    iso = serializers.DateField(help_text="Дата дня в формате YYYY-MM-DD.")
    dateLabel = serializers.CharField(required=False, help_text="Дата дня в пользовательском формате из настроек приложения.")
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
    defaultTimezone = serializers.CharField(help_text="Активный часовой пояс из настроек приложения пользователя.")
    openingBalanceRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Текущий остаток активных счетов пользователя.")
    openingBalanceLabel = serializers.CharField(required=False, help_text="Текущий остаток активных счетов в пользовательском формате числа.")


class FinancialCalendarExportColumnsSerializer(serializers.Serializer):
    actual = serializers.BooleanField(default=True, help_text="Включить фактический баланс в выгрузку.")
    balance = serializers.BooleanField(default=True, help_text="Включить прогнозный баланс на конец дня.")
    events = serializers.BooleanField(default=True, help_text="Включить краткое описание событий дня.")
    risks = serializers.BooleanField(default=True, help_text="Включить уровень риска по остатку на день.")


class FinancialCalendarExportPreviewRowSerializer(serializers.Serializer):
    date = serializers.CharField(help_text="Дата для отображения с учётом формата даты пользователя.")
    iso = serializers.DateField(required=False, help_text="ISO-дата строки выгрузки.")
    actualRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Фактический баланс. Для будущих дней возвращается 0.00.")
    forecastRub = serializers.DecimalField(max_digits=14, decimal_places=2, help_text="Прогнозный баланс на конец дня.")
    eventsSummary = serializers.CharField(help_text="Краткое описание событий дня.")
    riskLevel = serializers.ChoiceField(choices=FINANCIAL_CALENDAR_RISK_LEVEL_CHOICES, required=False, help_text="Уровень риска по остатку на день.")
    riskLabel = serializers.CharField(required=False, help_text="Подпись уровня риска для выгрузки.")


class FinancialCalendarExportPreviewResponseSerializer(serializers.Serializer):
    rows = FinancialCalendarExportPreviewRowSerializer(many=True, help_text="Строки предварительного просмотра выгрузки.")


class FinancialCalendarExportRequestSerializer(serializers.Serializer):
    year = serializers.IntegerField(required=True, min_value=2000, max_value=2100, help_text="Год календаря.")
    month = serializers.IntegerField(required=True, min_value=1, max_value=12, help_text="Месяц календаря, 1-12.")
    format = serializers.ChoiceField(
        choices=[("csv", "CSV"), ("pdf", "PDF"), ("xlsx", "XLSX")],
        required=False,
        default="csv",
        help_text="Формат файла выгрузки.",
    )
    columns = FinancialCalendarExportColumnsSerializer(required=False, help_text="Набор колонок, которые нужно включить в файл.")
    accountIds = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="ID счетов для фильтрации.",
    )
    eventTypes = serializers.ListField(
        child=serializers.ChoiceField(choices=FINANCIAL_CALENDAR_EVENT_TYPE_CHOICES),
        required=False,
        help_text="Типы событий для фильтрации.",
    )
    dateFrom = serializers.DateField(required=False, help_text="Нижняя граница периода выгрузки.")
    dateTo = serializers.DateField(required=False, help_text="Верхняя граница периода выгрузки.")
    timezone = serializers.CharField(required=False, help_text="IANA-часовой пояс. Если не передан, используется настройка пользователя.")


class FinancialCalendarExportResponseSerializer(serializers.Serializer):
    downloadUrl = serializers.CharField(help_text="Data URL с содержимым файла для скачивания на фронте.")
    fileName = serializers.CharField(help_text="Имя файла выгрузки.")
