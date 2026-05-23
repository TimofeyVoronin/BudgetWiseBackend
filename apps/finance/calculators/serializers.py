from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.finance.calculators.services import (
    CALCULATOR_CREDIT,
    CALCULATOR_DEPOSIT,
    CALCULATOR_IDS,
    CALCULATOR_INFLATION,
    CALCULATOR_INSTALLMENT,
    CALCULATOR_MORTGAGE,
    CALCULATOR_PENSION,
    DEPOSIT_CAPITALIZATION_MONTHLY,
    DEPOSIT_CAPITALIZATION_NONE,
    DEPOSIT_CAPITALIZATION_QUARTERLY,
    DEPOSIT_CAPITALIZATION_YEARLY,
    DEPOSIT_TOP_UP_MONTHLY,
    DEPOSIT_TOP_UP_NONE,
    PAYMENT_ANNUITY,
    PAYMENT_DIFFERENTIATED,
)


CALCULATOR_ID_CHOICES = [(value, value) for value in sorted(CALCULATOR_IDS)]
LOAN_PAYMENT_TYPE_CHOICES = [
    (PAYMENT_ANNUITY, "Аннуитетный"),
    (PAYMENT_DIFFERENTIATED, "Дифференцированный"),
]
DEPOSIT_CAPITALIZATION_CHOICES = [
    (DEPOSIT_CAPITALIZATION_NONE, "Нет"),
    (DEPOSIT_CAPITALIZATION_MONTHLY, "Ежемесячно"),
    (DEPOSIT_CAPITALIZATION_QUARTERLY, "Ежеквартально"),
    (DEPOSIT_CAPITALIZATION_YEARLY, "Ежегодно"),
]
DEPOSIT_TOP_UP_CHOICES = [
    (DEPOSIT_TOP_UP_NONE, "Нет"),
    (DEPOSIT_TOP_UP_MONTHLY, "Ежемесячно"),
]

MONEY_ERROR_MESSAGES = {
    "invalid": "Укажите сумму числом.",
    "min_value": "Сумма должна быть больше нуля.",
    "max_digits": "Сумма слишком большая.",
    "max_decimal_places": "Укажите не больше двух знаков после запятой.",
    "required": "Заполните сумму.",
    "null": "Заполните сумму.",
}
ZERO_MONEY_ERROR_MESSAGES = {
    **MONEY_ERROR_MESSAGES,
    "min_value": "Сумма не может быть отрицательной.",
}
RATE_ERROR_MESSAGES = {
    "invalid": "Укажите ставку числом.",
    "min_value": "Ставка не может быть отрицательной.",
    "max_value": "Ставка должна быть не больше 100%% годовых.",
    "max_digits": "Ставка слишком большая.",
    "max_decimal_places": "Укажите не больше четырёх знаков после запятой.",
    "required": "Заполните ставку.",
    "null": "Заполните ставку.",
}
TERM_MONTHS_ERROR_MESSAGES = {
    "invalid": "Укажите срок целым числом месяцев.",
    "min_value": "Срок должен быть не меньше 1 месяца.",
    "max_value": "Срок должен быть не больше 600 месяцев.",
    "required": "Заполните срок.",
    "null": "Заполните срок.",
}
TERM_YEARS_ERROR_MESSAGES = {
    "invalid": "Укажите срок целым числом лет.",
    "min_value": "Срок должен быть не меньше 1 года.",
    "max_value": "Срок должен быть не больше 50 лет.",
    "required": "Заполните срок.",
    "null": "Заполните срок.",
}
BOOLEAN_ERROR_MESSAGES = {
    "invalid": "Укажите значение true или false.",
    "required": "Заполните поле.",
    "null": "Заполните поле.",
}


def money_field(
    *,
    min_value: str = "1.00",
    required: bool = True,
    default=None,
    help_text: str = "Денежная сумма в рублях.",
) -> serializers.DecimalField:
    kwargs = {
        "max_digits": 14,
        "decimal_places": 2,
        "min_value": Decimal(min_value),
        "required": required,
        "error_messages": MONEY_ERROR_MESSAGES if Decimal(min_value) > 0 else ZERO_MONEY_ERROR_MESSAGES,
        "help_text": help_text,
    }
    if default is not None:
        kwargs["default"] = Decimal(default)
    return serializers.DecimalField(**kwargs)


def rate_field(help_text: str = "Годовая процентная ставка, от 0 до 100%.") -> serializers.DecimalField:
    return serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0.0000"),
        max_value=Decimal("100.0000"),
        error_messages=RATE_ERROR_MESSAGES,
        help_text=help_text,
    )


class CalculatorCatalogItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True, help_text="Идентификатор калькулятора.")
    title = serializers.CharField(read_only=True, help_text="Название карточки калькулятора.")
    description = serializers.CharField(read_only=True, help_text="Короткое описание калькулятора.")
    icon = serializers.CharField(read_only=True, help_text="Код иконки для карточки.")
    iconBg = serializers.CharField(read_only=True, help_text="HEX-фон плашки иконки.")
    iconColor = serializers.CharField(read_only=True, help_text="HEX-цвет иконки.")
    category = serializers.ChoiceField(
        choices=[("credit", "Кредиты"), ("saving", "Сбережения"), ("pension", "Пенсия")],
        read_only=True,
        help_text="Категория калькулятора для группировки на странице.",
    )
    routeTitle = serializers.CharField(read_only=True, help_text="Заголовок страницы калькулятора.")
    subtitle = serializers.CharField(read_only=True, help_text="Подзаголовок страницы калькулятора.")


class CalculatorsHubListResponseSerializer(serializers.Serializer):
    items = CalculatorCatalogItemSerializer(many=True, read_only=True, help_text="Доступные финансовые калькуляторы.")
    totalCount = serializers.IntegerField(read_only=True, help_text="Количество калькуляторов после фильтрации.")


class CreditCalculatorInputSerializer(serializers.Serializer):
    amount = money_field(help_text="Сумма кредита в рублях.")
    ratePct = rate_field(help_text="Годовая ставка по кредиту, %.")
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=600,
        error_messages=TERM_MONTHS_ERROR_MESSAGES,
        help_text="Срок кредита в месяцах, от 1 до 600.",
    )
    paymentType = serializers.ChoiceField(
        choices=LOAN_PAYMENT_TYPE_CHOICES,
        error_messages={
            "invalid_choice": "Выберите тип платежа: annuity или differentiated.",
            "required": "Выберите тип платежа.",
            "null": "Выберите тип платежа.",
        },
        help_text="Тип платежа: annuity или differentiated.",
    )
    issueDate = serializers.DateField(
        error_messages={
            "invalid": "Укажите дату выдачи в формате YYYY-MM-DD.",
            "required": "Укажите дату выдачи.",
            "null": "Укажите дату выдачи.",
        },
        help_text="Дата выдачи кредита в формате YYYY-MM-DD.",
    )


class MortgageCalculatorInputSerializer(serializers.Serializer):
    propertyPrice = money_field(help_text="Стоимость жилья в рублях.")
    downPaymentPct = serializers.DecimalField(
        max_digits=6,
        decimal_places=3,
        min_value=Decimal("0.000"),
        max_value=Decimal("90.000"),
        error_messages={
            "invalid": "Укажите первоначальный взнос числом.",
            "min_value": "Первоначальный взнос не может быть отрицательным.",
            "max_value": "Первоначальный взнос должен быть не больше 90%% стоимости жилья.",
            "max_digits": "Первоначальный взнос слишком большой.",
            "max_decimal_places": "Укажите не больше трёх знаков после запятой.",
            "required": "Заполните первоначальный взнос.",
            "null": "Заполните первоначальный взнос.",
        },
        help_text="Первоначальный взнос в процентах от стоимости жилья, от 0 до 90.",
    )
    ratePct = rate_field(help_text="Годовая ставка по ипотеке, %.")
    termYears = serializers.IntegerField(
        min_value=1,
        max_value=50,
        error_messages=TERM_YEARS_ERROR_MESSAGES,
        help_text="Срок ипотеки в годах, от 1 до 50.",
    )
    withInsurance = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES, help_text="Учитывать условную стоимость страхования.")
    isFamilyMortgage = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES, help_text="Флаг семейной ипотеки для интерфейса.")

    def validate(self, attrs):
        loan_amount = attrs["propertyPrice"] * (Decimal("100") - attrs["downPaymentPct"]) / Decimal("100")
        if loan_amount <= 0:
            raise serializers.ValidationError(
                {"downPaymentPct": "Сумма кредита после первоначального взноса должна быть больше нуля."}
            )
        return attrs


class InstallmentCalculatorInputSerializer(serializers.Serializer):
    price = money_field(help_text="Цена товара в рублях.")
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=120,
        error_messages={
            **TERM_MONTHS_ERROR_MESSAGES,
            "max_value": "Срок рассрочки должен быть не больше 120 месяцев.",
        },
        help_text="Срок рассрочки в месяцах, от 1 до 120.",
    )
    bankFeePct = rate_field(help_text="Комиссия банка в процентах.")
    downPayment = money_field(min_value="0.00", help_text="Первый взнос в рублях.")
    zeroOverpayment = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES, help_text="Считать рассрочку без переплаты.")

    def validate(self, attrs):
        if attrs["downPayment"] >= attrs["price"]:
            raise serializers.ValidationError(
                {"downPayment": "Первый взнос должен быть меньше цены товара."}
            )
        return attrs


class DepositCalculatorInputSerializer(serializers.Serializer):
    amount = money_field(help_text="Начальная сумма вклада в рублях.")
    ratePct = rate_field(help_text="Годовая ставка по вкладу, %.")
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=600,
        error_messages=TERM_MONTHS_ERROR_MESSAGES,
        help_text="Срок вклада в месяцах, от 1 до 600.",
    )
    capitalization = serializers.ChoiceField(
        choices=DEPOSIT_CAPITALIZATION_CHOICES,
        error_messages={
            "invalid_choice": "Выберите капитализацию: none, monthly, quarterly или yearly.",
            "required": "Выберите капитализацию.",
            "null": "Выберите капитализацию.",
        },
        help_text="Периодичность капитализации процентов.",
    )
    topUp = serializers.ChoiceField(
        choices=DEPOSIT_TOP_UP_CHOICES,
        error_messages={
            "invalid_choice": "Выберите тип пополнения: none или monthly.",
            "required": "Выберите тип пополнения.",
            "null": "Выберите тип пополнения.",
        },
        help_text="Тип пополнения вклада.",
    )
    monthlyTopUp = money_field(min_value="0.00", required=False, default="0.00", help_text="Ежемесячное пополнение в рублях, если topUp=monthly.")

    def validate(self, attrs):
        if attrs["topUp"] == DEPOSIT_TOP_UP_NONE:
            attrs["monthlyTopUp"] = Decimal("0.00")
        return attrs


class PensionCalculatorInputSerializer(serializers.Serializer):
    currentAge = serializers.IntegerField(
        min_value=14,
        max_value=100,
        error_messages={
            "invalid": "Укажите текущий возраст целым числом.",
            "min_value": "Текущий возраст должен быть не меньше 14 лет.",
            "max_value": "Текущий возраст должен быть не больше 100 лет.",
            "required": "Заполните текущий возраст.",
            "null": "Заполните текущий возраст.",
        },
        help_text="Текущий возраст пользователя.",
    )
    retireAge = serializers.IntegerField(
        min_value=15,
        max_value=100,
        error_messages={
            "invalid": "Укажите возраст выхода на пенсию целым числом.",
            "min_value": "Возраст выхода на пенсию должен быть не меньше 15 лет.",
            "max_value": "Возраст выхода на пенсию должен быть не больше 100 лет.",
            "required": "Заполните возраст выхода на пенсию.",
            "null": "Заполните возраст выхода на пенсию.",
        },
        help_text="Возраст выхода на пенсию.",
    )
    monthlyContribution = money_field(min_value="0.00", help_text="Ежемесячный взнос в пенсионные накопления.")
    returnRatePct = rate_field(help_text="Ожидаемая годовая доходность, %.")
    inflationPct = rate_field(help_text="Ожидаемая годовая инфляция, %.")
    initialSaved = money_field(min_value="0.00", help_text="Уже накопленная сумма в рублях.")

    def validate(self, attrs):
        if attrs["retireAge"] <= attrs["currentAge"]:
            raise serializers.ValidationError(
                {"retireAge": "Возраст выхода на пенсию должен быть больше текущего возраста."}
            )
        return attrs


class InflationCalculatorInputSerializer(serializers.Serializer):
    amount = money_field(help_text="Сумма сбережений в рублях.")
    years = serializers.IntegerField(
        min_value=1,
        max_value=100,
        error_messages={
            "invalid": "Укажите срок целым числом лет.",
            "min_value": "Срок должен быть не меньше 1 года.",
            "max_value": "Срок должен быть не больше 100 лет.",
            "required": "Заполните срок.",
            "null": "Заполните срок.",
        },
        help_text="Срок расчёта инфляции в годах, от 1 до 100.",
    )
    inflationPct = rate_field(help_text="Годовая инфляция, %.")


class PaymentScheduleRowSerializer(serializers.Serializer):
    month = serializers.IntegerField(read_only=True, help_text="Номер месяца платежа.")
    date = serializers.DateField(read_only=True, required=False, help_text="Дата платежа, если она рассчитана.")
    payment = serializers.FloatField(read_only=True, help_text="Сумма платежа за месяц, ₽.")
    principalPart = serializers.FloatField(read_only=True, help_text="Часть платежа, которая гасит основной долг, ₽.")
    interestPart = serializers.FloatField(read_only=True, help_text="Процентная часть платежа, ₽.")
    remaining = serializers.FloatField(read_only=True, help_text="Остаток долга после платежа, ₽.")


class DepositGrowthPointSerializer(serializers.Serializer):
    month = serializers.IntegerField(read_only=True, help_text="Номер месяца роста вклада.")
    label = serializers.CharField(read_only=True, help_text="Подпись точки графика.")
    total = serializers.FloatField(read_only=True, help_text="Итоговая сумма вклада на этом месяце, ₽.")


class PensionCapitalPointSerializer(serializers.Serializer):
    age = serializers.IntegerField(read_only=True, help_text="Возраст на точке графика.")
    contributions = serializers.FloatField(read_only=True, help_text="Накопленные взносы, ₽.")
    growth = serializers.FloatField(read_only=True, help_text="Инвестиционный доход, ₽.")
    total = serializers.FloatField(read_only=True, help_text="Итоговый капитал, ₽.")


class CreditCalculationResultSerializer(serializers.Serializer):
    monthlyPayment = serializers.FloatField(read_only=True, help_text="Основной месячный платёж для отображения, ₽.")
    firstPayment = serializers.FloatField(read_only=True, help_text="Первый платёж по графику, ₽.")
    lastPayment = serializers.FloatField(read_only=True, help_text="Последний платёж по графику, ₽.")
    totalPayment = serializers.FloatField(read_only=True, help_text="Общая сумма выплат, ₽.")
    overpayment = serializers.FloatField(read_only=True, help_text="Переплата по кредиту, ₽.")
    schedule = PaymentScheduleRowSerializer(many=True, read_only=True, help_text="График платежей.")


class MortgageCalculationResultSerializer(serializers.Serializer):
    loanAmount = serializers.FloatField(read_only=True, help_text="Сумма ипотечного кредита после первоначального взноса, ₽.")
    monthlyPayment = serializers.FloatField(read_only=True, help_text="Ежемесячный платёж, ₽.")
    recommendedIncome = serializers.FloatField(read_only=True, help_text="Рекомендуемый месячный доход, ₽.")
    totalPayment = serializers.FloatField(read_only=True, help_text="Общая сумма выплат, ₽.")
    totalInterest = serializers.FloatField(read_only=True, help_text="Переплата за весь срок, ₽.")
    principalShare = serializers.FloatField(read_only=True, help_text="Доля основного долга в общей сумме выплат.")
    interestShare = serializers.FloatField(read_only=True, help_text="Доля процентов и страхования в общей сумме выплат.")


class InstallmentCalculationSliceSerializer(serializers.Serializer):
    monthlyPayment = serializers.FloatField(read_only=True, help_text="Платёж в месяц, ₽.")
    totalToPay = serializers.FloatField(read_only=True, help_text="Итоговая сумма к оплате, ₽.")
    overpayment = serializers.FloatField(read_only=True, help_text="Переплата, ₽.")
    overpaymentPct = serializers.FloatField(read_only=True, help_text="Переплата в процентах.")


class InstallmentCardComparisonMetaSerializer(serializers.Serializer):
    annualRatePct = serializers.FloatField(read_only=True, help_text="Ставка кредитной карты для сравнения, %.")
    minPaymentPct = serializers.FloatField(read_only=True, help_text="Минимальный платёж кредитной карты, %.")
    footerNote = serializers.CharField(read_only=True, help_text="Пояснение к сравнению с кредитной картой.")


class InstallmentCalculationResultSerializer(serializers.Serializer):
    installment = InstallmentCalculationSliceSerializer(read_only=True, help_text="Расчёт рассрочки.")
    creditCard = InstallmentCalculationSliceSerializer(read_only=True, help_text="Сравнение с кредитной картой.")
    comparisonMeta = InstallmentCardComparisonMetaSerializer(read_only=True, help_text="Метаданные сравнения.")


class DepositCalculationResultSerializer(serializers.Serializer):
    income = serializers.FloatField(read_only=True, help_text="Процентный доход по вкладу, ₽.")
    finalAmount = serializers.FloatField(read_only=True, help_text="Итоговая сумма вклада, ₽.")
    effectiveRatePct = serializers.FloatField(read_only=True, help_text="Эффективная годовая ставка, %.")
    series = DepositGrowthPointSerializer(many=True, read_only=True, help_text="Точки графика роста вклада.")


class PensionCalculationResultSerializer(serializers.Serializer):
    capitalAtRetirement = serializers.FloatField(read_only=True, help_text="Номинальный капитал к пенсионному возрасту, ₽.")
    monthlyPensionReal = serializers.FloatField(read_only=True, help_text="Оценка ежемесячной пенсии в реальных ценах, ₽.")
    series = PensionCapitalPointSerializer(many=True, read_only=True, help_text="Динамика капитала по возрастам.")


class InflationCalculationResultSerializer(serializers.Serializer):
    futureValue = serializers.FloatField(read_only=True, help_text="Покупательная способность суммы через указанный срок, ₽.")
    purchasingPowerLoss = serializers.FloatField(read_only=True, help_text="Потеря покупательной способности, ₽.")
    lossPct = serializers.FloatField(read_only=True, help_text="Потеря покупательной способности, %.")


class CalculatorDefaultsResponseSerializer(serializers.Serializer):
    calculatorId = serializers.CharField(read_only=True, help_text="Идентификатор калькулятора.")
    defaults = serializers.DictField(read_only=True, help_text="Значения формы по умолчанию.")


class CalculatorValidationErrorResponseSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    fieldErrors = serializers.DictField(child=serializers.CharField(), read_only=True)
    fieldWarnings = serializers.DictField(child=serializers.CharField(), read_only=True, required=False)


class CalculatorAPIErrorInnerSerializer(serializers.Serializer):
    status_code = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    field_errors = serializers.DictField(child=serializers.ListField(child=serializers.CharField()), read_only=True, allow_null=True)
    detail = serializers.JSONField(read_only=True, allow_null=True)
    trace_id = serializers.CharField(read_only=True, allow_null=True)


class CalculatorAPIErrorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField(read_only=True)
    error = CalculatorAPIErrorInnerSerializer(read_only=True)


CALCULATOR_INPUT_SERIALIZERS = {
    CALCULATOR_CREDIT: CreditCalculatorInputSerializer,
    CALCULATOR_MORTGAGE: MortgageCalculatorInputSerializer,
    CALCULATOR_INSTALLMENT: InstallmentCalculatorInputSerializer,
    CALCULATOR_DEPOSIT: DepositCalculatorInputSerializer,
    CALCULATOR_PENSION: PensionCalculatorInputSerializer,
    CALCULATOR_INFLATION: InflationCalculatorInputSerializer,
}

CALCULATOR_RESULT_SERIALIZERS = {
    CALCULATOR_CREDIT: CreditCalculationResultSerializer,
    CALCULATOR_MORTGAGE: MortgageCalculationResultSerializer,
    CALCULATOR_INSTALLMENT: InstallmentCalculationResultSerializer,
    CALCULATOR_DEPOSIT: DepositCalculationResultSerializer,
    CALCULATOR_PENSION: PensionCalculationResultSerializer,
    CALCULATOR_INFLATION: InflationCalculationResultSerializer,
}
