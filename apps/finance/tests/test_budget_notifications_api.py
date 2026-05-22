from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status

from apps.finance.models import (
    Budget,
    BudgetKind,
    BudgetNotificationChannel,
    BudgetNotificationEvent,
    BudgetNotificationEventStatus,
    BudgetNotificationEventType,
    BudgetNotificationSettings,
    BudgetPeriodType,
    Goal,
    GoalCategory,
    GoalPriority,
    GoalStatus,
    Notification,
    NotificationDeliveryStatus,
    NotificationEntityKind,
    default_budget_notification_anti_spam,
    default_budget_notification_channels,
    default_budget_notification_events,
    default_budget_notification_goals,
    default_budget_notification_thresholds,
)
from apps.finance.tests.base import FinanceAPITestCase


class BudgetNotificationsAPITests(FinanceAPITestCase):
    SETTINGS_URL = "/api/v1/finance/budget-notifications/settings/"
    VALIDATE_THRESHOLDS_URL = "/api/v1/finance/budget-notifications/settings/validate-thresholds/"
    TEST_URL = "/api/v1/finance/budget-notifications/settings/test/"
    PREVIEW_URL = "/api/v1/finance/budget-notifications/settings/preview/"
    META_URL = "/api/v1/finance/budget-notifications/meta/"
    CHECK_URL = "/api/v1/finance/budget-notifications/check/"
    NOTIFICATIONS_URL = "/api/v1/finance/notifications/"

    def create_budget(self, *, limit="10000.00", category=None, start=None, end=None):
        start = start or self.today.replace(day=1)
        end = end or (self.today + timedelta(days=20))
        return Budget.objects.create(
            user=self.user,
            category=category or self.expense_category,
            period_type=BudgetPeriodType.MONTH,
            period_start=start,
            period_end=end,
            amount_limit=Decimal(limit),
            currency="RUB",
            kind=BudgetKind.EXPENSE,
        )

    def spend_for_budget(self, *, budget, amount="8500.00"):
        return self.create_transaction(
            category=budget.category,
            type=budget.kind,
            amount=amount,
            description="Расход по бюджетному уведомлению",
            operation_date=self.today,
        )

    def create_goal(self, *, name="Отпуск", target="100000.00", current="50000.00", deadline=None, status_value=GoalStatus.ACTIVE):
        return Goal.objects.create(
            user=self.user,
            name=name,
            category=GoalCategory.TRAVEL,
            priority=GoalPriority.MEDIUM,
            target_amount=Decimal(target),
            current_amount=Decimal(current),
            deadline=deadline,
            status=status_value,
        )

    def enable_settings(
        self,
        *,
        enabled=True,
        thresholds_enabled=True,
        event_enabled=None,
        channel_enabled=None,
        goals_update=None,
        anti_spam_update=None,
    ):
        settings, _ = BudgetNotificationSettings.objects.get_or_create(user=self.user)
        settings.enabled = enabled
        settings.thresholds_enabled = thresholds_enabled
        settings.thresholds = deepcopy(default_budget_notification_thresholds())
        settings.events = deepcopy(default_budget_notification_events())
        settings.channels = deepcopy(default_budget_notification_channels())
        settings.anti_spam = deepcopy(default_budget_notification_anti_spam())
        settings.goals = deepcopy(default_budget_notification_goals())

        if event_enabled:
            for item in settings.events:
                event_id = item["id"]
                if event_id in event_enabled:
                    item["enabled"] = event_enabled[event_id]

        if channel_enabled:
            for item in settings.channels:
                channel_id = item["id"]
                if channel_id in channel_enabled:
                    item["enabled"] = channel_enabled[channel_id]

        if goals_update:
            settings.goals.update(goals_update)

        if anti_spam_update:
            settings.anti_spam.update(anti_spam_update)

        settings.full_clean()
        settings.save()
        return settings

    def run_check(self, *, dry_run=False, target_date=None):
        return self.client.post(
            self.CHECK_URL,
            {
                "date": (target_date or self.today).isoformat(),
                "dryRun": dry_run,
            },
            format="json",
        )

    def event_types(self, response):
        return [item["eventType"] for item in response.data["items"]]

    def test_budget_notification_settings_requires_authentication(self):
        response = self.client.get(self.SETTINGS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_settings_meta_preview_test_and_threshold_validation_endpoints(self):
        self.authenticate()
        goal = self.create_goal(name="Подушка", current="25000.00")

        get_response = self.client.get(self.SETTINGS_URL)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertFalse(get_response.data["enabled"])
        self.assertEqual(get_response.data["thresholds"][0]["id"], "near_limit")

        patch_response = self.client.patch(
            self.SETTINGS_URL,
            {
                "enabled": True,
                "thresholdsEnabled": True,
                "channels": [
                    {"id": BudgetNotificationChannel.IN_APP, "enabled": True},
                    {"id": BudgetNotificationChannel.EMAIL, "enabled": True},
                    {"id": BudgetNotificationChannel.PUSH, "enabled": True},
                ],
                "goals": {
                    "selectedGoalIds": [goal.id],
                    "notifyOnLag": True,
                    "lagDays": 7,
                },
            },
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertTrue(patch_response.data["enabled"])
        self.assertEqual(patch_response.data["goals"]["selectedGoalIds"], [goal.id])

        invalid_thresholds_response = self.client.post(
            self.VALIDATE_THRESHOLDS_URL,
            {
                "thresholds": [
                    {"id": "near_limit", "percent": 90, "active": True},
                    {"id": "warning", "percent": 80, "active": True},
                ]
            },
            format="json",
        )
        self.assertEqual(invalid_thresholds_response.status_code, status.HTTP_200_OK)
        self.assertFalse(invalid_thresholds_response.data["ok"])
        self.assertIn("thresholds", invalid_thresholds_response.data["fieldErrors"])

        preview_response = self.client.get(self.PREVIEW_URL)
        self.assertEqual(preview_response.status_code, status.HTTP_200_OK)
        self.assertIn(BudgetNotificationChannel.IN_APP, preview_response.data["activeChannelIds"])

        test_response = self.client.post(
            self.TEST_URL,
            {
                "channelIds": [
                    BudgetNotificationChannel.IN_APP,
                    BudgetNotificationChannel.EMAIL,
                    BudgetNotificationChannel.PUSH,
                ],
                "eventId": BudgetNotificationEventType.BUDGET_NEAR_LIMIT,
            },
            format="json",
        )
        self.assertEqual(test_response.status_code, status.HTTP_200_OK)
        statuses_by_channel = {item["id"]: item["status"] for item in test_response.data["channels"]}
        self.assertEqual(statuses_by_channel[BudgetNotificationChannel.IN_APP], "delivered")
        self.assertEqual(statuses_by_channel[BudgetNotificationChannel.EMAIL], "skipped")
        self.assertEqual(statuses_by_channel[BudgetNotificationChannel.PUSH], "skipped")

        meta_response = self.client.get(self.META_URL)
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertIn(goal.id, [item["id"] for item in meta_response.data["goals"]])
        self.assertIn(24, [item["value"] for item in meta_response.data["repeatHourOptions"]])

    def test_check_dry_run_returns_events_without_creating_rows_or_notifications(self):
        self.authenticate()
        self.enable_settings()
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")

        response = self.run_check(dry_run=True)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["dryRun"])
        self.assertEqual(response.data["createdEvents"], 0)
        self.assertEqual(response.data["wouldCreateEvents"], 1)
        self.assertEqual(response.data["deliveredNotifications"], 0)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.BUDGET_NEAR_LIMIT])
        self.assertEqual(BudgetNotificationEvent.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

    def test_check_creates_budget_near_limit_event_and_in_app_notification(self):
        self.authenticate()
        self.enable_settings(
            channel_enabled={
                BudgetNotificationChannel.IN_APP: True,
                BudgetNotificationChannel.EMAIL: True,
                BudgetNotificationChannel.PUSH: True,
            }
        )
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["createdEvents"], 1)
        self.assertEqual(response.data["deliveredNotifications"], 1)
        self.assertEqual(response.data["skippedDeliveries"], 2)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.BUDGET_NEAR_LIMIT])

        event = BudgetNotificationEvent.objects.get(user=self.user)
        self.assertEqual(event.status, BudgetNotificationEventStatus.DELIVERED)
        self.assertEqual(event.event_type, BudgetNotificationEventType.BUDGET_NEAR_LIMIT)
        self.assertEqual(event.related_object_type, NotificationEntityKind.BUDGET)
        self.assertEqual(event.related_object_id, budget.id)
        self.assertIn("deliveryResults", event.payload)

        notification = Notification.objects.get(user=self.user)
        self.assertEqual(notification.delivery_status, NotificationDeliveryStatus.DELIVERED)
        self.assertEqual(notification.entity_kind, NotificationEntityKind.BUDGET)
        self.assertEqual(notification.entity_id, budget.id)
        self.assertEqual(notification.entity_label, budget.category.name)

        notifications_response = self.client.get(self.NOTIFICATIONS_URL)
        self.assertEqual(notifications_response.status_code, status.HTTP_200_OK)
        self.assertEqual(notifications_response.data["count"], 1)
        self.assertEqual(notifications_response.data["results"][0]["title"], "Бюджет близок к лимиту")

    def test_duplicate_protection_skips_recently_created_event(self):
        self.authenticate()
        self.enable_settings()
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")

        first_response = self.run_check()
        second_response = self.run_check()

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["createdEvents"], 1)
        self.assertEqual(second_response.data["createdEvents"], 0)
        self.assertEqual(second_response.data["skippedDuplicates"], 1)
        self.assertEqual(BudgetNotificationEvent.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_budget_exceeded_event_has_higher_priority_than_near_limit(self):
        self.authenticate()
        self.enable_settings()
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="12000.00")

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["createdEvents"], 1)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.BUDGET_EXCEEDED])
        self.assertEqual(response.data["items"][0]["thresholdId"], "exceeded")

    def test_budget_back_to_normal_event_is_generated_after_previous_risk_event(self):
        self.authenticate()
        self.enable_settings(
            event_enabled={
                BudgetNotificationEventType.BUDGET_BACK_TO_NORMAL: True,
            }
        )
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="5000.00")
        BudgetNotificationEvent.objects.create(
            user=self.user,
            event_type=BudgetNotificationEventType.BUDGET_NEAR_LIMIT,
            related_object_type=NotificationEntityKind.BUDGET,
            related_object_id=budget.id,
            threshold_id="near_limit",
            title="Старое предупреждение",
            message="Бюджет ранее был близок к лимиту.",
            icon="trending-up",
            icon_tone="warning",
            status=BudgetNotificationEventStatus.DELIVERED,
            deduplication_key=f"budget_near_limit:budget:{budget.id}:near_limit",
            payload={},
        )

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(BudgetNotificationEventType.BUDGET_BACK_TO_NORMAL, self.event_types(response))

    def test_goal_milestone_event_is_generated_for_selected_goal(self):
        self.authenticate()
        goal = self.create_goal(current="50000.00", target="100000.00")
        self.enable_settings(
            goals_update={
                "selectedGoalIds": [goal.id],
            }
        )

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["processedGoals"], 1)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.GOAL_MILESTONE])
        self.assertEqual(response.data["items"][0]["thresholdId"], "milestone_50")

    def test_goal_reached_event_is_generated_for_completed_goal(self):
        self.authenticate()
        goal = self.create_goal(current="100000.00", target="100000.00")
        self.enable_settings(
            goals_update={
                "selectedGoalIds": [goal.id],
            }
        )

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.GOAL_REACHED])
        self.assertEqual(response.data["items"][0]["thresholdId"], "reached")

    def test_goal_lagging_event_is_generated_when_lagging_notifications_are_enabled(self):
        self.authenticate()
        goal = self.create_goal(
            current="10000.00",
            target="100000.00",
            deadline=self.today + timedelta(days=7),
        )
        self.enable_settings(
            event_enabled={
                BudgetNotificationEventType.GOAL_LAGGING: True,
            },
            goals_update={
                "selectedGoalIds": [goal.id],
                "notifyOnLag": True,
                "lagDays": 7,
            },
        )

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.event_types(response), [BudgetNotificationEventType.GOAL_LAGGING])
        self.assertEqual(response.data["items"][0]["thresholdId"], "lag_7_days")

    def test_disabled_settings_do_not_process_budgets_or_goals(self):
        self.authenticate()
        self.enable_settings(enabled=False)
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")
        self.create_goal(current="50000.00", target="100000.00")

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["processedBudgets"], 0)
        self.assertEqual(response.data["processedGoals"], 0)
        self.assertEqual(response.data["createdEvents"], 0)
        self.assertEqual(response.data["items"], [])

    def test_disabled_event_type_does_not_create_matching_event(self):
        self.authenticate()
        self.enable_settings(
            event_enabled={
                BudgetNotificationEventType.BUDGET_NEAR_LIMIT: False,
            }
        )
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["processedBudgets"], 1)
        self.assertEqual(response.data["createdEvents"], 0)
        self.assertEqual(response.data["items"], [])

    def test_disabled_in_app_channel_skips_delivery_without_creating_notification(self):
        self.authenticate()
        self.enable_settings(
            channel_enabled={
                BudgetNotificationChannel.IN_APP: False,
            }
        )
        budget = self.create_budget()
        self.spend_for_budget(budget=budget, amount="8500.00")

        response = self.run_check()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["createdEvents"], 1)
        self.assertEqual(response.data["deliveredNotifications"], 0)
        self.assertEqual(response.data["skippedDeliveries"], 1)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)

        event = BudgetNotificationEvent.objects.get(user=self.user)
        self.assertEqual(event.status, BudgetNotificationEventStatus.SKIPPED)
        delivery_result = event.payload["deliveryResults"][0]
        self.assertEqual(delivery_result["channel"], BudgetNotificationChannel.IN_APP)
        self.assertEqual(delivery_result["status"], "skipped")

    def test_foreign_goal_in_settings_is_rejected(self):
        self.authenticate()
        other_goal = Goal.objects.create(
            user=self.other_user,
            name="Чужая цель",
            category=GoalCategory.SAVINGS,
            priority=GoalPriority.LOW,
            target_amount=Decimal("50000.00"),
            current_amount=Decimal("10000.00"),
        )

        response = self.client.patch(
            self.SETTINGS_URL,
            {
                "goals": {
                    "selectedGoalIds": [other_goal.id],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("goals.selectedGoalIds", response.data["error"]["field_errors"])
