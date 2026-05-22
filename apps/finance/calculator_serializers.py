from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.finance.calculators import (
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
    "max_value": "Ставка должна быть не больше 100% годовых.",
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


def money_field(*, min_value: str = "1.00", required: bool = True, default=None) -> serializers.DecimalField:
    kwargs = {
        "max_digits": 14,
        "decimal_places": 2,
        "min_value": Decimal(min_value),
        "required": required,
        "error_messages": MONEY_ERROR_MESSAGES if Decimal(min_value) > 0 else ZERO_MONEY_ERROR_MESSAGES,
    }
    if default is not None:
        kwargs["default"] = Decimal(default)
    return serializers.DecimalField(**kwargs)


def rate_field() -> serializers.DecimalField:
    return serializers.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0.0000"),
        max_value=Decimal("100.0000"),
        error_messages=RATE_ERROR_MESSAGES,
    )


class CalculatorCatalogItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    icon = serializers.CharField(read_only=True)
    iconBg = serializers.CharField(read_only=True)
    iconColor = serializers.CharField(read_only=True)
    category = serializers.ChoiceField(
        choices=[("credit", "Кредиты"), ("saving", "Сбережения"), ("pension", "Пенсия")],
        read_only=True,
    )
    routeTitle = serializers.CharField(read_only=True)
    subtitle = serializers.CharField(read_only=True)


class CalculatorsHubListResponseSerializer(serializers.Serializer):
    items = CalculatorCatalogItemSerializer(many=True, read_only=True)
    totalCount = serializers.IntegerField(read_only=True)


class CreditCalculatorInputSerializer(serializers.Serializer):
    amount = money_field()
    ratePct = rate_field()
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=600,
        error_messages=TERM_MONTHS_ERROR_MESSAGES,
    )
    paymentType = serializers.ChoiceField(
        choices=LOAN_PAYMENT_TYPE_CHOICES,
        error_messages={
            "invalid_choice": "Выберите тип платежа: annuity или differentiated.",
            "required": "Выберите тип платежа.",
            "null": "Выберите тип платежа.",
        },
    )
    issueDate = serializers.DateField(
        error_messages={
            "invalid": "Укажите дату выдачи в формате YYYY-MM-DD.",
            "required": "Укажите дату выдачи.",
            "null": "Укажите дату выдачи.",
        }
    )


class MortgageCalculatorInputSerializer(serializers.Serializer):
    propertyPrice = money_field()
    downPaymentPct = serializers.DecimalField(
        max_digits=6,
        decimal_places=3,
        min_value=Decimal("0.000"),
        max_value=Decimal("90.000"),
        error_messages={
            "invalid": "Укажите первоначальный взнос числом.",
            "min_value": "Первоначальный взнос не может быть отрицательным.",
            "max_value": "Первоначальный взнос должен быть не больше 90% стоимости жилья.",
            "max_digits": "Первоначальный взнос слишком большой.",
            "max_decimal_places": "Укажите не больше трёх знаков после запятой.",
            "required": "Заполните первоначальный взнос.",
            "null": "Заполните первоначальный взнос.",
        },
    )
    ratePct = rate_field()
    termYears = serializers.IntegerField(
        min_value=1,
        max_value=50,
        error_messages=TERM_YEARS_ERROR_MESSAGES,
    )
    withInsurance = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES)
    isFamilyMortgage = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES)

    def validate(self, attrs):
        loan_amount = attrs["propertyPrice"] * (Decimal("100") - attrs["downPaymentPct"]) / Decimal("100")
        if loan_amount <= 0:
            raise serializers.ValidationError(
                {"downPaymentPct": "Сумма кредита после первоначального взноса должна быть больше нуля."}
            )
        return attrs


class InstallmentCalculatorInputSerializer(serializers.Serializer):
    price = money_field()
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=120,
        error_messages={
            **TERM_MONTHS_ERROR_MESSAGES,
            "max_value": "Срок рассрочки должен быть не больше 120 месяцев.",
        },
    )
    bankFeePct = rate_field()
    downPayment = money_field(min_value="0.00")
    zeroOverpayment = serializers.BooleanField(error_messages=BOOLEAN_ERROR_MESSAGES)

    def validate(self, attrs):
        if attrs["downPayment"] >= attrs["price"]:
            raise serializers.ValidationError(
                {"downPayment": "Первый взнос должен быть меньше цены товара."}
            )
        return attrs


class DepositCalculatorInputSerializer(serializers.Serializer):
    amount = money_field()
    ratePct = rate_field()
    termMonths = serializers.IntegerField(
        min_value=1,
        max_value=600,
        error_messages=TERM_MONTHS_ERROR_MESSAGES,
    )
    capitalization = serializers.ChoiceField(
        choices=DEPOSIT_CAPITALIZATION_CHOICES,
        error_messages={
            "invalid_choice": "Выберите капитализацию: none, monthly, quarterly или yearly.",
            "required": "Выберите капитализацию.",
            "null": "Выберите капитализацию.",
        },
    )
    topUp = serializers.ChoiceField(
        choices=DEPOSIT_TOP_UP_CHOICES,
        error_messages={
            "invalid_choice": "Выберите тип пополнения: none или monthly.",
            "required": "Выберите тип пополнения.",
            "null": "Выберите тип пополнения.",
        },
    )
    monthlyTopUp = money_field(min_value="0.00", required=False, default="0.00")

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
    )
    monthlyContribution = money_field(min_value="0.00")
    returnRatePct = rate_field()
    inflationPct = rate_field()
    initialSaved = money_field(min_value="0.00")

    def validate(self, attrs):
        if attrs["retireAge"] <= attrs["currentAge"]:
            raise serializers.ValidationError(
                {"retireAge": "Возраст выхода на пенсию должен быть больше текущего возраста."}
            )
        return attrs


class InflationCalculatorInputSerializer(serializers.Serializer):
    amount = money_field()
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
    )
    inflationPct = rate_field()


class PaymentScheduleRowSerializer(serializers.Serializer):
    month = serializers.IntegerField(read_only=True)
    date = serializers.DateField(read_only=True, required=False)
    payment = serializers.FloatField(read_only=True)
    principalPart = serializers.FloatField(read_only=True)
    interestPart = serializers.FloatField(read_only=True)
    remaining = serializers.FloatField(read_only=True)


class DepositGrowthPointSerializer(serializers.Serializer):
    month = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)
    total = serializers.FloatField(read_only=True)


class PensionCapitalPointSerializer(serializers.Serializer):
    age = serializers.IntegerField(read_only=True)
    contributions = serializers.FloatField(read_only=True)
    growth = serializers.FloatField(read_only=True)
    total = serializers.FloatField(read_only=True)


class CreditCalculationResultSerializer(serializers.Serializer):
    monthlyPayment = serializers.FloatField(read_only=True)
    firstPayment = serializers.FloatField(read_only=True)
    lastPayment = serializers.FloatField(read_only=True)
    totalPayment = serializers.FloatField(read_only=True)
    overpayment = serializers.FloatField(read_only=True)
    schedule = PaymentScheduleRowSerializer(many=True, read_only=True)


class MortgageCalculationResultSerializer(serializers.Serializer):
    loanAmount = serializers.FloatField(read_only=True)
    monthlyPayment = serializers.FloatField(read_only=True)
    recommendedIncome = serializers.FloatField(read_only=True)
    totalPayment = serializers.FloatField(read_only=True)
    totalInterest = serializers.FloatField(read_only=True)
    principalShare = serializers.FloatField(read_only=True)
    interestShare = serializers.FloatField(read_only=True)


class InstallmentCalculationSliceSerializer(serializers.Serializer):
    monthlyPayment = serializers.FloatField(read_only=True)
    totalToPay = serializers.FloatField(read_only=True)
    overpayment = serializers.FloatField(read_only=True)
    overpaymentPct = serializers.FloatField(read_only=True)


class InstallmentCardComparisonMetaSerializer(serializers.Serializer):
    annualRatePct = serializers.FloatField(read_only=True)
    minPaymentPct = serializers.FloatField(read_only=True)
    footerNote = serializers.CharField(read_only=True)


class InstallmentCalculationResultSerializer(serializers.Serializer):
    installment = InstallmentCalculationSliceSerializer(read_only=True)
    creditCard = InstallmentCalculationSliceSerializer(read_only=True)
    comparisonMeta = InstallmentCardComparisonMetaSerializer(read_only=True)


class DepositCalculationResultSerializer(serializers.Serializer):
    income = serializers.FloatField(read_only=True)
    finalAmount = serializers.FloatField(read_only=True)
    effectiveRatePct = serializers.FloatField(read_only=True)
    series = DepositGrowthPointSerializer(many=True, read_only=True)


class PensionCalculationResultSerializer(serializers.Serializer):
    capitalAtRetirement = serializers.FloatField(read_only=True)
    monthlyPensionReal = serializers.FloatField(read_only=True)
    series = PensionCapitalPointSerializer(many=True, read_only=True)


class InflationCalculationResultSerializer(serializers.Serializer):
    futureValue = serializers.FloatField(read_only=True)
    purchasingPowerLoss = serializers.FloatField(read_only=True)
    lossPct = serializers.FloatField(read_only=True)


class CalculatorDefaultsResponseSerializer(serializers.Serializer):
    calculatorId = serializers.CharField(read_only=True)
    defaults = serializers.DictField(read_only=True)


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
