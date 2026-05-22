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
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    ratePct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    termMonths = serializers.IntegerField(min_value=1, max_value=600)
    paymentType = serializers.ChoiceField(choices=LOAN_PAYMENT_TYPE_CHOICES)
    issueDate = serializers.DateField()


class MortgageCalculatorInputSerializer(serializers.Serializer):
    propertyPrice = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    downPaymentPct = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=Decimal("0.000"), max_value=Decimal("90.000"))
    ratePct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    termYears = serializers.IntegerField(min_value=1, max_value=50)
    withInsurance = serializers.BooleanField()
    isFamilyMortgage = serializers.BooleanField()


class InstallmentCalculatorInputSerializer(serializers.Serializer):
    price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    termMonths = serializers.IntegerField(min_value=1, max_value=120)
    bankFeePct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    downPayment = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))
    zeroOverpayment = serializers.BooleanField()

    def validate(self, attrs):
        if attrs["downPayment"] >= attrs["price"]:
            raise serializers.ValidationError(
                {"downPayment": "Первый взнос должен быть меньше цены товара."}
            )
        return attrs


class DepositCalculatorInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    ratePct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    termMonths = serializers.IntegerField(min_value=1, max_value=600)
    capitalization = serializers.ChoiceField(choices=DEPOSIT_CAPITALIZATION_CHOICES)
    topUp = serializers.ChoiceField(choices=DEPOSIT_TOP_UP_CHOICES)
    monthlyTopUp = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        default=Decimal("0.00"),
    )


class PensionCalculatorInputSerializer(serializers.Serializer):
    currentAge = serializers.IntegerField(min_value=14, max_value=100)
    retireAge = serializers.IntegerField(min_value=15, max_value=100)
    monthlyContribution = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))
    returnRatePct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    inflationPct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))
    initialSaved = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.00"))

    def validate(self, attrs):
        if attrs["retireAge"] <= attrs["currentAge"]:
            raise serializers.ValidationError(
                {"retireAge": "Возраст выхода на пенсию должен быть больше текущего возраста."}
            )
        return attrs


class InflationCalculatorInputSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("1.00"))
    years = serializers.IntegerField(min_value=1, max_value=100)
    inflationPct = serializers.DecimalField(max_digits=7, decimal_places=4, min_value=Decimal("0.0000"), max_value=Decimal("100.0000"))


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
    code = serializers.ChoiceField(choices=[("VALIDATION_FAILED", "Ошибка валидации")], read_only=True)
    message = serializers.CharField(read_only=True)
    fieldErrors = serializers.DictField(child=serializers.CharField(), read_only=True)
    fieldWarnings = serializers.DictField(child=serializers.CharField(), read_only=True, required=False)


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
