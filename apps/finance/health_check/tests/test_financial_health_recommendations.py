from django.test import SimpleTestCase

from apps.finance.health_check.constants import (
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
    FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM,
    METRIC_BUDGET_USAGE,
    METRIC_CASH_GAP_RISK,
    METRIC_EMERGENCY_FUND_PROGRESS,
    METRIC_EXPENSE_STABILITY,
    METRIC_INCOME_EXPENSE_RATIO,
    METRIC_PLANNED_PAYMENTS_LOAD,
    METRIC_SAVINGS_RATE,
    RECOMMENDATION_BUDGET_OVER_LIMIT,
    RECOMMENDATION_CASH_GAP_RISK,
    RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD,
    RECOMMENDATION_LOW_SAVINGS_RATE,
    RECOMMENDATION_NEGATIVE_NET_BALANCE,
    RECOMMENDATION_UNSTABLE_EXPENSES,
    RECOMMENDATION_WEAK_EMERGENCY_FUND,
)
from apps.finance.health_check.recommendations import (
    build_financial_health_recommendations,
)


class FinancialHealthRecommendationTests(SimpleTestCase):
    def test_recommendations_are_generated_from_weak_metrics(self):
        recommendations = build_financial_health_recommendations(
            totals={
                "netBalance": {
                    "amount": -5000.0,
                    "currency": "RUB",
                },
            },
            metrics=[
                _metric(METRIC_INCOME_EXPENSE_RATIO, score=35),
                _metric(
                    METRIC_SAVINGS_RATE,
                    value=3.0,
                    score=60,
                    details={
                        "income": {
                            "amount": 100000.0,
                            "currency": "RUB",
                        },
                    },
                ),
                _metric(
                    METRIC_BUDGET_USAGE,
                    value=125.0,
                    score=20,
                    details={
                        "budgetCount": 1,
                        "overLimit": True,
                    },
                ),
                _metric(
                    METRIC_EMERGENCY_FUND_PROGRESS,
                    value=20.0,
                    score=35,
                    details={
                        "goalCount": 1,
                    },
                ),
                _metric(
                    METRIC_CASH_GAP_RISK,
                    value=3000.0,
                    score=20,
                    details={
                        "hasCashGapRisk": True,
                    },
                ),
                _metric(METRIC_PLANNED_PAYMENTS_LOAD, value=65.0, score=45),
                _metric(
                    METRIC_EXPENSE_STABILITY,
                    value=20.0,
                    score=45,
                    details={
                        "daysWithExpenses": 2,
                    },
                ),
            ],
            data_quality={
                "hasEnoughData": True,
            },
            max_items=10,
        )

        codes = [item["code"] for item in recommendations]

        self.assertIn(RECOMMENDATION_NEGATIVE_NET_BALANCE, codes)
        self.assertIn(RECOMMENDATION_CASH_GAP_RISK, codes)
        self.assertIn(RECOMMENDATION_BUDGET_OVER_LIMIT, codes)
        self.assertIn(RECOMMENDATION_LOW_SAVINGS_RATE, codes)
        self.assertIn(RECOMMENDATION_WEAK_EMERGENCY_FUND, codes)
        self.assertEqual(len(recommendations), 7)
        self.assertEqual(
            recommendations[0]["priority"],
            FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_HIGH,
        )
        self.assertTrue(
            all(
                {
                    "code",
                    "priority",
                    "metricId",
                    "title",
                    "text",
                    "action",
                    "reason",
                }.issubset(item)
                for item in recommendations
            )
        )

    def test_recommendations_are_empty_for_healthy_metrics(self):
        recommendations = build_financial_health_recommendations(
            totals={
                "netBalance": {
                    "amount": 40000.0,
                    "currency": "RUB",
                },
            },
            metrics=[
                _metric(METRIC_INCOME_EXPENSE_RATIO, value=2.5, score=100),
                _metric(METRIC_SAVINGS_RATE, value=35.0, score=100),
                _metric(
                    METRIC_BUDGET_USAGE,
                    value=55.0,
                    score=100,
                    details={
                        "budgetCount": 1,
                        "overLimit": False,
                    },
                ),
                _metric(
                    METRIC_EMERGENCY_FUND_PROGRESS,
                    value=100.0,
                    score=100,
                    details={
                        "goalCount": 1,
                    },
                ),
                _metric(
                    METRIC_CASH_GAP_RISK,
                    value=0.0,
                    score=100,
                    details={
                        "hasCashGapRisk": False,
                    },
                ),
                _metric(METRIC_PLANNED_PAYMENTS_LOAD, value=5.0, score=100),
                _metric(
                    METRIC_EXPENSE_STABILITY,
                    value=90.0,
                    score=100,
                    details={
                        "daysWithExpenses": 10,
                    },
                ),
            ],
            data_quality={
                "hasEnoughData": True,
            },
        )

        self.assertEqual(recommendations, [])

    def test_medium_priority_recommendations_are_supported(self):
        recommendations = build_financial_health_recommendations(
            metrics=[
                _metric(METRIC_PLANNED_PAYMENTS_LOAD, value=45.0, score=55),
                _metric(
                    METRIC_EXPENSE_STABILITY,
                    value=35.0,
                    score=60,
                    details={
                        "daysWithExpenses": 3,
                    },
                ),
            ],
        )

        codes = {item["code"] for item in recommendations}

        self.assertIn(RECOMMENDATION_HIGH_PLANNED_PAYMENTS_LOAD, codes)
        self.assertIn(RECOMMENDATION_UNSTABLE_EXPENSES, codes)
        self.assertTrue(
            all(
                item["priority"] == FINANCIAL_HEALTH_RECOMMENDATION_PRIORITY_MEDIUM
                for item in recommendations
            )
        )


def _metric(
    metric_id,
    *,
    value=None,
    score,
    level="warning",
    details=None,
):
    return {
        "id": metric_id,
        "label": metric_id,
        "description": "",
        "category": "",
        "weight": 1,
        "unit": "score",
        "higherIsBetter": True,
        "value": value,
        "score": score,
        "level": level,
        "details": details or {},
    }
