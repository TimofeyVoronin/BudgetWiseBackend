from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finance.calculator_serializers import (
    CALCULATOR_INPUT_SERIALIZERS,
    CalculatorDefaultsResponseSerializer,
    CalculatorsHubListResponseSerializer,
    CreditCalculationResultSerializer,
    CreditCalculatorInputSerializer,
    DepositCalculationResultSerializer,
    DepositCalculatorInputSerializer,
    InflationCalculationResultSerializer,
    InflationCalculatorInputSerializer,
    InstallmentCalculationResultSerializer,
    InstallmentCalculatorInputSerializer,
    MortgageCalculationResultSerializer,
    MortgageCalculatorInputSerializer,
    PensionCalculationResultSerializer,
    PensionCalculatorInputSerializer,
)
from apps.finance.calculators import (
    CALCULATOR_CREDIT,
    CALCULATOR_DEPOSIT,
    CALCULATOR_INFLATION,
    CALCULATOR_INSTALLMENT,
    CALCULATOR_MORTGAGE,
    CALCULATOR_PENSION,
    CalculatorNotFoundError,
    calculate_financial_calculator,
    get_calculator_defaults,
    get_calculators_catalog,
)


CALCULATOR_TAG = "finance-calculators"

CALCULATE_REQUEST_SERIALIZER = PolymorphicProxySerializer(
    component_name="CalculatorCalculateRequest",
    serializers=[
        CreditCalculatorInputSerializer,
        MortgageCalculatorInputSerializer,
        InstallmentCalculatorInputSerializer,
        DepositCalculatorInputSerializer,
        PensionCalculatorInputSerializer,
        InflationCalculatorInputSerializer,
    ],
    resource_type_field_name=None,
)

CALCULATE_RESPONSE_SERIALIZER = PolymorphicProxySerializer(
    component_name="CalculatorCalculateResponse",
    serializers=[
        CreditCalculationResultSerializer,
        MortgageCalculationResultSerializer,
        InstallmentCalculationResultSerializer,
        DepositCalculationResultSerializer,
        PensionCalculationResultSerializer,
        InflationCalculationResultSerializer,
    ],
    resource_type_field_name=None,
)


class CalculatorsHubView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[CALCULATOR_TAG],
        summary="Получить каталог финансовых калькуляторов",
        description=(
            "Возвращает список доступных stateless-калькуляторов для страницы "
            "финансовых калькуляторов. Расчёты не сохраняются в базе данных."
        ),
        parameters=[
            OpenApiParameter(
                "q",
                OpenApiTypes.STR,
                description="Поиск по названию, описанию или идентификатору калькулятора.",
            )
        ],
        responses={200: CalculatorsHubListResponseSerializer},
        examples=[
            OpenApiExample(
                "Каталог калькуляторов",
                value={
                    "items": [
                        {
                            "id": "credit",
                            "title": "Кредит",
                            "description": "Рассчитайте ежемесячный платёж и переплату по кредиту",
                            "icon": "percent",
                            "iconBg": "#F3E8FF",
                            "iconColor": "#4F46E5",
                            "category": "credit",
                            "routeTitle": "Кредитный калькулятор",
                            "subtitle": "Рассчитайте ежемесячный платёж и переплату по кредиту",
                        }
                    ],
                    "totalCount": 6,
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        items = get_calculators_catalog(request.query_params.get("q"))
        return Response({"items": items, "totalCount": len(items)})


class CalculatorDefaultsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[CALCULATOR_TAG],
        summary="Получить значения по умолчанию для калькулятора",
        description=(
            "Возвращает стартовые параметры формы выбранного калькулятора. "
            "Поддерживаемые calcId: credit, mortgage, installment, deposit, pension, inflation."
        ),
        responses={
            200: CalculatorDefaultsResponseSerializer,
            404: OpenApiResponse(description="Калькулятор не найден."),
        },
        examples=[
            OpenApiExample(
                "Значения по умолчанию для кредита",
                value={
                    "calculatorId": "credit",
                    "defaults": {
                        "amount": 1500000,
                        "ratePct": 12.5,
                        "termMonths": 36,
                        "paymentType": "annuity",
                        "issueDate": "2026-05-22",
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, calc_id: str):
        try:
            payload = get_calculator_defaults(calc_id)
        except CalculatorNotFoundError as exc:
            raise NotFound("Калькулятор не найден.") from exc
        return Response(payload)


class CalculatorCalculateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[CALCULATOR_TAG],
        summary="Выполнить расчёт финансового калькулятора",
        description=(
            "Выполняет расчёт по выбранному калькулятору. Endpoint не сохраняет результат в базе. "
            "Схема тела запроса зависит от calcId: credit, mortgage, installment, deposit, pension, inflation."
        ),
        request=CALCULATE_REQUEST_SERIALIZER,
        responses={
            200: CALCULATE_RESPONSE_SERIALIZER,
            400: OpenApiResponse(description="Ошибка валидации входных параметров."),
            404: OpenApiResponse(description="Калькулятор не найден."),
        },
        examples=[
            OpenApiExample(
                "Расчёт кредита",
                value={
                    "amount": 1500000,
                    "ratePct": 12.5,
                    "termMonths": 36,
                    "paymentType": "annuity",
                    "issueDate": "2026-05-22",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Результат кредита",
                value={
                    "monthlyPayment": 50180.0,
                    "firstPayment": 50180.0,
                    "lastPayment": 50180.0,
                    "totalPayment": 1806480.0,
                    "overpayment": 306480.0,
                    "schedule": [
                        {
                            "month": 1,
                            "date": "2026-06-22",
                            "payment": 50180.0,
                            "principalPart": 34555.0,
                            "interestPart": 15625.0,
                            "remaining": 1465445.0,
                        }
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, calc_id: str):
        serializer_class = CALCULATOR_INPUT_SERIALIZERS.get(calc_id)
        if serializer_class is None:
            raise NotFound("Калькулятор не найден.")

        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = calculate_financial_calculator(calc_id, serializer.validated_data)
        return Response(result, status=status.HTTP_200_OK)
