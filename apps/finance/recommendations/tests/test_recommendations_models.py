from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.finance.models import (
    FinancialRecommendation,
    FinancialRecommendationEvent,
    FinancialRecommendationEventType,
    FinancialRecommendationPriority,
    FinancialRecommendationSource,
    FinancialRecommendationStatus,
    FinancialRecommendationType,
)
from apps.finance.recommendations.constants import (
    RECOMMENDATION_CODE_CREATE_BUDGET,
    RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
)


User = get_user_model()


class FinancialRecommendationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recommendation-user",
            email="recommendation-user@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-recommendation-user",
            email="other-recommendation-user@example.com",
            password="StrongPass123!",
        )

    def create_recommendation(self, **kwargs):
        data = {
            "user": self.user,
            "code": RECOMMENDATION_CODE_CREATE_BUDGET,
            "type": FinancialRecommendationType.BUDGET,
            "priority": FinancialRecommendationPriority.MEDIUM,
            "status": FinancialRecommendationStatus.ACTIVE,
            "title": "Создайте бюджет",
            "text": "Настройте бюджет для контроля расходов.",
            "action": "Создать бюджет",
            "reason": "Нет активных бюджетов.",
            "source": FinancialRecommendationSource.FINANCIAL_HEALTH,
            "source_key": "budget-missing",
            "context": {"metricId": "budgetUsage"},
        }
        data.update(kwargs)
        recommendation = FinancialRecommendation(**data)
        recommendation.full_clean()
        recommendation.save()
        return recommendation

    def test_recommendation_can_be_created_with_required_fields(self):
        recommendation = self.create_recommendation()

        self.assertEqual(recommendation.user, self.user)
        self.assertEqual(recommendation.code, RECOMMENDATION_CODE_CREATE_BUDGET)
        self.assertEqual(recommendation.type, FinancialRecommendationType.BUDGET)
        self.assertEqual(recommendation.priority, FinancialRecommendationPriority.MEDIUM)
        self.assertEqual(recommendation.status, FinancialRecommendationStatus.ACTIVE)
        self.assertEqual(recommendation.context["metricId"], "budgetUsage")
        self.assertFalse(recommendation.is_terminal)
        self.assertTrue(recommendation.is_visible)

    def test_recommendation_rejects_invalid_choice_values(self):
        recommendation = FinancialRecommendation(
            user=self.user,
            code="unknown_code",
            type="unknown_type",
            priority="unknown_priority",
            status="unknown_status",
            title="Некорректная рекомендация",
            text="Текст",
            source="unknown_source",
            context=[],
        )

        with self.assertRaises(ValidationError) as context:
            recommendation.full_clean()

        errors = context.exception.message_dict
        self.assertIn("code", errors)
        self.assertIn("type", errors)
        self.assertIn("priority", errors)
        self.assertIn("status", errors)
        self.assertIn("source", errors)
        self.assertIn("context", errors)

    def test_duplicate_active_recommendations_are_protected(self):
        self.create_recommendation()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinancialRecommendation.objects.create(
                    user=self.user,
                    code=RECOMMENDATION_CODE_CREATE_BUDGET,
                    type=FinancialRecommendationType.BUDGET,
                    priority=FinancialRecommendationPriority.MEDIUM,
                    status=FinancialRecommendationStatus.ACTIVE,
                    title="Дубль бюджета",
                    text="Повторная рекомендация.",
                    source=FinancialRecommendationSource.FINANCIAL_HEALTH,
                    source_key="budget-missing",
                )

    def test_duplicate_terminal_recommendations_are_allowed(self):
        first = self.create_recommendation(status=FinancialRecommendationStatus.ACCEPTED)
        second = self.create_recommendation(status=FinancialRecommendationStatus.ACCEPTED)

        self.assertNotEqual(first.id, second.id)
        self.assertTrue(first.is_terminal)
        self.assertTrue(second.is_terminal)

    def test_duplicate_recommendations_for_different_users_are_allowed(self):
        first = self.create_recommendation()
        second = self.create_recommendation(user=self.other_user)

        self.assertNotEqual(first.user_id, second.user_id)

    def test_accept_and_hide_statuses_set_timestamps_on_clean(self):
        accepted = FinancialRecommendation(
            user=self.user,
            code=RECOMMENDATION_CODE_INCREASE_SAVINGS_RATE,
            type=FinancialRecommendationType.SAVING,
            priority=FinancialRecommendationPriority.HIGH,
            status=FinancialRecommendationStatus.ACCEPTED,
            title="Увеличьте долю сбережений",
            text="Откладывайте часть дохода.",
            source=FinancialRecommendationSource.TRANSACTIONS,
            source_key="savings-rate",
        )
        accepted.full_clean()
        accepted.save()

        hidden = FinancialRecommendation(
            user=self.user,
            code=RECOMMENDATION_CODE_CREATE_BUDGET,
            type=FinancialRecommendationType.BUDGET,
            priority=FinancialRecommendationPriority.LOW,
            status=FinancialRecommendationStatus.HIDDEN,
            title="Создайте бюджет",
            text="Настройте бюджет.",
            source=FinancialRecommendationSource.BUDGETS,
            source_key="hidden-budget",
        )
        hidden.full_clean()
        hidden.save()

        self.assertIsNotNone(accepted.accepted_at)
        self.assertIsNone(accepted.hidden_at)
        self.assertIsNotNone(hidden.hidden_at)
        self.assertIsNone(hidden.accepted_at)

    def test_snoozed_recommendation_becomes_visible_after_snooze_date(self):
        future = self.create_recommendation(
            source_key="future-snooze",
            status=FinancialRecommendationStatus.SNOOZED,
            snoozed_until=timezone.now() + timedelta(days=1),
        )
        past = self.create_recommendation(
            source_key="past-snooze",
            status=FinancialRecommendationStatus.SNOOZED,
            snoozed_until=timezone.now() - timedelta(minutes=1),
        )

        self.assertFalse(future.is_visible)
        self.assertTrue(past.is_visible)


class FinancialRecommendationEventModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recommendation-event-user",
            email="recommendation-event-user@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-recommendation-event-user",
            email="other-recommendation-event-user@example.com",
            password="StrongPass123!",
        )
        self.recommendation = FinancialRecommendation.objects.create(
            user=self.user,
            code=RECOMMENDATION_CODE_CREATE_BUDGET,
            type=FinancialRecommendationType.BUDGET,
            priority=FinancialRecommendationPriority.MEDIUM,
            status=FinancialRecommendationStatus.ACTIVE,
            title="Создайте бюджет",
            text="Настройте бюджет для контроля расходов.",
            action="Создать бюджет",
            reason="Нет активных бюджетов.",
            source=FinancialRecommendationSource.FINANCIAL_HEALTH,
            source_key="budget-missing",
            context={"metricId": "budgetUsage"},
        )

    def test_event_can_be_created_for_recommendation_owner(self):
        event = FinancialRecommendationEvent(
            recommendation=self.recommendation,
            user=self.user,
            event_type=FinancialRecommendationEventType.VIEWED,
            metadata={"surface": "recommendations_page"},
        )
        event.full_clean()
        event.save()

        self.assertEqual(event.recommendation, self.recommendation)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.metadata["surface"], "recommendations_page")
        self.assertEqual(self.recommendation.events.count(), 1)

    def test_event_rejects_invalid_event_type_and_metadata(self):
        event = FinancialRecommendationEvent(
            recommendation=self.recommendation,
            user=self.user,
            event_type="unknown_event",
            metadata=[],
        )

        with self.assertRaises(ValidationError) as context:
            event.full_clean()

        errors = context.exception.message_dict
        self.assertIn("event_type", errors)
        self.assertIn("metadata", errors)

    def test_event_user_must_match_recommendation_user(self):
        event = FinancialRecommendationEvent(
            recommendation=self.recommendation,
            user=self.other_user,
            event_type=FinancialRecommendationEventType.ACCEPTED,
            metadata={},
        )

        with self.assertRaises(ValidationError) as context:
            event.full_clean()

        self.assertIn("user", context.exception.message_dict)
