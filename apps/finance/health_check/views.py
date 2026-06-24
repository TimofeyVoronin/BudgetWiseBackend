from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.finance.health_check.constants import FINANCIAL_HEALTH_TAG
from apps.finance.health_check.contracts import build_financial_health_meta
from apps.finance.health_check.scoring import build_financial_health_summary
from apps.finance.health_check.serializers import (
    FinancialHealthMetaResponseSerializer,
    FinancialHealthSummaryQuerySerializer,
    FinancialHealthSummaryResponseSerializer,
)


class FinancialHealthMetaView(GenericAPIView):
    serializer_class = FinancialHealthMetaResponseSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_HEALTH_TAG],
        operation_id="finance_health_check_meta_retrieve",
        summary="Получить справочник Financial Health Check",
        description=(
            "Возвращает описание метрик финансового здоровья, уровней score, "
            "доступных периодов, приоритетов рекомендаций и контракт summary-ответа. "
            "Endpoint нужен frontend для построения страницы Financial Health Check "
            "без жёсткой привязки к списку метрик в интерфейсе."
        ),
        responses={
            200: FinancialHealthMetaResponseSerializer,
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Meta response",
                value={
                    "scoreRange": {"min": 0, "max": 100},
                    "defaultPeriod": "month",
                    "defaultCurrency": "RUB",
                    "periods": [
                        {
                            "value": "month",
                            "label": "Месяц",
                            "requiresCustomDates": False,
                        }
                    ],
                    "levels": [
                        {
                            "value": "good",
                            "label": "Хорошее состояние",
                            "minScore": 75,
                            "maxScore": 89,
                            "description": "Большинство финансовых показателей в норме.",
                        }
                    ],
                    "metrics": [
                        {
                            "id": "savingsRate",
                            "label": "Доля сбережений",
                            "description": "Показывает, какая часть доходов остаётся после расходов.",
                            "category": "cashflow",
                            "weight": 18,
                            "unit": "percent",
                            "higherIsBetter": True,
                            "source": "transactions",
                        }
                    ],
                    "recommendationPriorities": [
                        {
                            "value": "high",
                            "label": "Высокий приоритет",
                            "description": "Рекомендация связана с высоким риском.",
                        }
                    ],
                    "summaryContract": {
                        "score": "integer 0..100",
                        "level": "excellent|good|warning|risk|critical",
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(build_financial_health_meta())
        return Response(serializer.data)


class FinancialHealthSummaryView(GenericAPIView):
    serializer_class = FinancialHealthSummaryResponseSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=[FINANCIAL_HEALTH_TAG],
        operation_id="finance_health_check_summary_retrieve",
        summary="Получить итоговую оценку финансового здоровья",
        description=(
            "Рассчитывает Financial Health Check для текущего пользователя. "
            "Endpoint возвращает общий score 0..100, уровень финансового здоровья, "
            "агрегированные суммы, детализацию по метрикам, rule-based рекомендации "
            "и служебную информацию о качестве данных. Расчёт read-only: он не создаёт "
            "и не изменяет счета, операции, бюджеты, цели или планируемые операции."
        ),
        parameters=[
            OpenApiParameter(
                "period",
                OpenApiTypes.STR,
                description="Период расчёта: month, quarter, year или custom. По умолчанию month.",
            ),
            OpenApiParameter(
                "date_from",
                OpenApiTypes.DATE,
                description="Дата начала периода в формате YYYY-MM-DD. Обязательна для period=custom.",
            ),
            OpenApiParameter(
                "date_to",
                OpenApiTypes.DATE,
                description="Дата окончания периода в формате YYYY-MM-DD. Обязательна для period=custom.",
            ),
            OpenApiParameter(
                "currency",
                OpenApiTypes.STR,
                description="ISO-код валюты отображения, например RUB. По умолчанию берётся валюта пользователя.",
            ),
        ],
        responses={
            200: FinancialHealthSummaryResponseSerializer,
            400: OpenApiResponse(description="Некорректные параметры расчёта."),
            401: OpenApiResponse(description="Пользователь не авторизован."),
        },
        examples=[
            OpenApiExample(
                "Summary response",
                value={
                    "score": 52,
                    "level": "risk",
                    "period": {
                        "type": "month",
                        "dateFrom": "2026-06-01",
                        "dateTo": "2026-06-25",
                        "label": "Текущий месяц",
                        "days": 25,
                    },
                    "currency": "RUB",
                    "totals": {
                        "income": {"amount": 0.0, "currency": "RUB"},
                        "expenses": {"amount": 250.0, "currency": "RUB"},
                        "netBalance": {"amount": -250.0, "currency": "RUB"},
                        "accountsBalance": {"amount": 236630.0, "currency": "RUB"},
                        "availableBalance": {"amount": 236630.0, "currency": "RUB"},
                    },
                    "metrics": [
                        {
                            "id": "incomeExpenseRatio",
                            "label": "Соотношение доходов и расходов",
                            "description": "Показывает, насколько доходы покрывают расходы.",
                            "category": "cashflow",
                            "weight": 20,
                            "unit": "ratio",
                            "higherIsBetter": True,
                            "value": 0.0,
                            "score": 15,
                            "level": "critical",
                            "details": {},
                        }
                    ],
                    "recommendations": [
                        {
                            "code": "negative_net_balance",
                            "priority": "high",
                            "metricId": "incomeExpenseRatio",
                            "title": "Расходы превышают доходы",
                            "text": "За выбранный период расходы оказались выше доходов.",
                            "action": "Проверьте крупные траты и временно сократите необязательные расходы.",
                            "reason": "totals.netBalance.amount<0",
                        }
                    ],
                    "dataQuality": {
                        "hasEnoughData": True,
                        "transactionCount": 25,
                        "accountCount": 3,
                        "budgetCount": 0,
                        "goalCount": 1,
                        "plannedTransactionCount": 0,
                        "periodDays": 25,
                        "warnings": ["Нет активных бюджетов за выбранный период."],
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        query_serializer = FinancialHealthSummaryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        params = query_serializer.validated_data
        payload = build_financial_health_summary(
            user=request.user,
            period=params.get("period") or None,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            currency=params.get("currency") or None,
        )
        response_serializer = self.get_serializer(payload)
        return Response(response_serializer.data)
