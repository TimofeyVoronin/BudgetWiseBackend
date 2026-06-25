from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import (
    Account,
    AccountType,
    Budget,
    Category,
    FinancialRecommendation,
    FinancialRecommendationEvent,
    FinancialRecommendationEventType,
    FinancialRecommendationStatus,
    FinancialRecommendationType,
    Transaction,
    TransactionType,
)
from apps.finance.recommendations.constants import (
    RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
    RECOMMENDATION_CODE_CREATE_BUDGET,
    RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL,
    RECOMMENDATION_CODE_FIX_CASH_GAP_RISK,
    RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
    RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES,
)
from apps.finance.recommendations.generator import generate_financial_recommendations
from apps.users.models import OnboardingSurvey, OnboardingSurveyStatus

User = get_user_model()


def build_summary(*, recommendations=None, data_quality=None):
    return {
        "score": 55,
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
            "income": {"amount": 100000, "currency": "RUB"},
            "expenses": {"amount": 95000, "currency": "RUB"},
            "netBalance": {"amount": 5000, "currency": "RUB"},
        },
        "metrics": [],
        "recommendations": recommendations or [],
        "dataQuality": data_quality
        or {
            "hasEnoughData": True,
            "transactionCount": 10,
            "accountCount": 1,
            "budgetCount": 0,
            "goalCount": 0,
            "plannedTransactionCount": 0,
            "periodDays": 25,
            "warnings": [],
        },
    }


class FinancialRecommendationGeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recommendation-generator-user",
            email="recommendation-generator-user@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-recommendation-generator-user",
            email="other-recommendation-generator-user@example.com",
            password="StrongPass123!",
        )

    def test_generator_creates_recommendations_from_financial_health_and_onboarding(self):
        summary = build_summary(
            recommendations=[
                {
                    "code": "low_savings_rate",
                    "priority": "medium",
                    "metricId": "savingsRate",
                    "title": "Низкая доля сбережений",
                    "text": "После расходов остаётся мало дохода.",
                    "action": "Откладывайте 10% дохода.",
                    "reason": "savingsRate.score<75",
                },
                {
                    "code": "unstable_expenses",
                    "priority": "high",
                    "metricId": "expenseStability",
                    "title": "Расходы распределены неравномерно",
                    "text": "Есть дни с высокими расходами.",
                    "action": "Проверьте крупные траты.",
                    "reason": "expenseStability.score<65",
                },
                {
                    "code": "cash_gap_risk",
                    "priority": "high",
                    "metricId": "cashGapRisk",
                    "title": "Есть риск кассового разрыва",
                    "text": "Остаток может стать отрицательным.",
                    "action": "Перенесите часть платежей.",
                    "reason": "cashGapRisk.hasCashGapRisk=true",
                },
            ]
        )

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=summary,
        ):
            result = generate_financial_recommendations(user=self.user)

        codes = set(
            FinancialRecommendation.objects.filter(user=self.user).values_list("code", flat=True)
        )

        self.assertEqual(result.created, 6)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(FinancialRecommendation.objects.filter(user=self.user).count(), 6)
        self.assertIn(RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE, codes)
        self.assertIn(RECOMMENDATION_CODE_REDUCE_UNSTABLE_EXPENSES, codes)
        self.assertIn(RECOMMENDATION_CODE_FIX_CASH_GAP_RISK, codes)
        self.assertIn(RECOMMENDATION_CODE_CREATE_BUDGET, codes)
        self.assertIn(RECOMMENDATION_CODE_CREATE_EMERGENCY_FUND_GOAL, codes)
        self.assertIn(RECOMMENDATION_CODE_COMPLETE_ONBOARDING, codes)
        self.assertEqual(
            FinancialRecommendationEvent.objects.filter(
                user=self.user,
                event_type=FinancialRecommendationEventType.CREATED,
            ).count(),
            6,
        )

    def test_completed_onboarding_does_not_create_onboarding_recommendation(self):
        OnboardingSurvey.objects.create(
            user=self.user,
            status=OnboardingSurveyStatus.COMPLETED,
            answers={"mainGoal": "expense_control"},
        )
        summary = build_summary(
            recommendations=[],
            data_quality={
                "hasEnoughData": True,
                "transactionCount": 5,
                "accountCount": 1,
                "budgetCount": 1,
                "goalCount": 1,
                "plannedTransactionCount": 0,
                "periodDays": 25,
                "warnings": [],
            },
        )

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=summary,
        ):
            result = generate_financial_recommendations(user=self.user)

        self.assertEqual(result.created, 0)
        self.assertFalse(
            FinancialRecommendation.objects.filter(
                user=self.user,
                code=RECOMMENDATION_CODE_COMPLETE_ONBOARDING,
            ).exists()
        )

    def test_repeated_generation_updates_existing_active_recommendation_without_duplicates(self):
        first_summary = build_summary(
            recommendations=[
                {
                    "code": "low_savings_rate",
                    "priority": "medium",
                    "metricId": "savingsRate",
                    "title": "Низкая доля сбережений",
                    "text": "Первый текст.",
                    "action": "Первое действие.",
                    "reason": "savingsRate.score<75",
                }
            ],
            data_quality={
                "hasEnoughData": True,
                "transactionCount": 5,
                "accountCount": 1,
                "budgetCount": 1,
                "goalCount": 1,
                "plannedTransactionCount": 0,
                "periodDays": 25,
                "warnings": [],
            },
        )
        second_summary = build_summary(
            recommendations=[
                {
                    "code": "low_savings_rate",
                    "priority": "high",
                    "metricId": "savingsRate",
                    "title": "Низкая доля сбережений",
                    "text": "Обновлённый текст.",
                    "action": "Обновлённое действие.",
                    "reason": "savingsRate.score<75",
                }
            ],
            data_quality=first_summary["dataQuality"],
        )

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=first_summary,
        ):
            first_result = generate_financial_recommendations(user=self.user)

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=second_summary,
        ):
            second_result = generate_financial_recommendations(user=self.user)

        recommendation = FinancialRecommendation.objects.get(
            user=self.user,
            code=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
        )
        self.assertEqual(first_result.created, 2)  # savings + onboarding
        self.assertEqual(second_result.created, 0)
        self.assertEqual(second_result.updated, 2)
        self.assertEqual(
            FinancialRecommendation.objects.filter(
                user=self.user,
                code=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
            ).count(),
            1,
        )
        self.assertEqual(recommendation.priority, "high")
        self.assertEqual(recommendation.text, "Обновлённый текст.")
        self.assertTrue(
            recommendation.events.filter(event_type=FinancialRecommendationEventType.REFRESHED).exists()
        )

    def test_hidden_recommendation_is_not_recreated_by_refresh(self):
        summary = build_summary(
            recommendations=[
                {
                    "code": "low_savings_rate",
                    "priority": "medium",
                    "metricId": "savingsRate",
                    "title": "Низкая доля сбережений",
                    "text": "После расходов остаётся мало дохода.",
                    "action": "Откладывайте 10% дохода.",
                    "reason": "savingsRate.score<75",
                }
            ],
            data_quality={
                "hasEnoughData": True,
                "transactionCount": 5,
                "accountCount": 1,
                "budgetCount": 1,
                "goalCount": 1,
                "plannedTransactionCount": 0,
                "periodDays": 25,
                "warnings": [],
            },
        )
        hidden = FinancialRecommendation.objects.create(
            user=self.user,
            code=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
            type=FinancialRecommendationType.SAVING,
            priority="medium",
            status=FinancialRecommendationStatus.HIDDEN,
            title="Низкая доля сбережений",
            text="Скрытая рекомендация.",
            source="financial_health",
            source_key="financial-health:savings-rate",
            context={},
        )

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=summary,
        ):
            result = generate_financial_recommendations(user=self.user)

        self.assertEqual(result.created, 1)  # only onboarding, hidden savings is respected
        self.assertEqual(result.skipped, 1)
        self.assertEqual(
            FinancialRecommendation.objects.filter(
                user=self.user,
                code=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
            ).count(),
            1,
        )
        hidden.refresh_from_db()
        self.assertEqual(hidden.status, FinancialRecommendationStatus.HIDDEN)

    def test_generator_isolated_by_user(self):
        summary = build_summary(
            recommendations=[
                {
                    "code": "cash_gap_risk",
                    "priority": "high",
                    "metricId": "cashGapRisk",
                    "title": "Есть риск кассового разрыва",
                    "text": "Остаток может стать отрицательным.",
                    "action": "Перенесите часть платежей.",
                    "reason": "cashGapRisk.hasCashGapRisk=true",
                }
            ],
            data_quality={
                "hasEnoughData": True,
                "transactionCount": 5,
                "accountCount": 1,
                "budgetCount": 1,
                "goalCount": 1,
                "plannedTransactionCount": 0,
                "periodDays": 25,
                "warnings": [],
            },
        )

        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=summary,
        ):
            generate_financial_recommendations(user=self.user)

        self.assertEqual(FinancialRecommendation.objects.filter(user=self.user).count(), 2)
        self.assertEqual(FinancialRecommendation.objects.filter(user=self.other_user).count(), 0)

    def test_generator_does_not_modify_financial_entities(self):
        account = Account.objects.create(
            user=self.user,
            name="Generator account",
            type=AccountType.CARD,
            initial_balance="10000.00",
            balance="10000.00",
            currency="RUB",
        )
        category = Category.objects.create(
            user=self.user,
            name="Food",
            type=TransactionType.EXPENSE,
        )
        Transaction.objects.create(
            user=self.user,
            account=account,
            category=category,
            type=TransactionType.EXPENSE,
            amount="1000.00",
            operation_date="2026-06-10",
        )
        budget = Budget.objects.create(
            user=self.user,
            category=category,
            period_type="month",
            amount_limit="5000.00",
            period_start="2026-06-01",
            period_end="2026-06-30",
            currency="RUB",
            kind="expense",
        )
        summary = build_summary(
            recommendations=[
                {
                    "code": "budget_over_limit",
                    "priority": "high",
                    "metricId": "budgetUsage",
                    "title": "Бюджет требует внимания",
                    "text": "Расходы приблизились к лимиту.",
                    "action": "Проверьте категории.",
                    "reason": "budgetUsage.score<70",
                }
            ],
            data_quality={
                "hasEnoughData": True,
                "transactionCount": 1,
                "accountCount": 1,
                "budgetCount": 1,
                "goalCount": 1,
                "plannedTransactionCount": 0,
                "periodDays": 25,
                "warnings": [],
            },
        )

        before = {
            "account_balance": Decimal(str(account.balance)),
            "transaction_count": Transaction.objects.filter(user=self.user).count(),
            "budget_count": Budget.objects.filter(user=self.user).count(),
        }
        with patch(
            "apps.finance.recommendations.generator.build_financial_health_summary",
            return_value=summary,
        ):
            generate_financial_recommendations(user=self.user)

        account.refresh_from_db()
        budget.refresh_from_db()
        self.assertEqual(account.balance, before["account_balance"])
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), before["transaction_count"])
        self.assertEqual(Budget.objects.filter(user=self.user).count(), before["budget_count"])
        self.assertEqual(budget.amount_limit, Decimal("5000.00"))
