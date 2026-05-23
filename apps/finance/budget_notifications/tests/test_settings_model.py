from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.finance.models import (
    BudgetNotificationChannel,
    BudgetNotificationEventType,
    BudgetNotificationSettings,
    Goal,
    GoalCategory,
    GoalPriority,
)


User = get_user_model()


class BudgetNotificationSettingsModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="budget-notifications",
            email="budget-notifications@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="other-budget-notifications",
            email="other-budget-notifications@example.com",
            password="StrongPass123!",
        )

    def test_default_settings_match_budget_notifications_form(self):
        settings = BudgetNotificationSettings.objects.create(user=self.user)

        self.assertFalse(settings.enabled)
        self.assertTrue(settings.thresholds_enabled)
        self.assertEqual(settings.preview_usage_percent, 87)

        threshold_ids = [item["id"] for item in settings.thresholds]
        self.assertEqual(threshold_ids, ["near_limit", "warning", "critical"])
        self.assertEqual(settings.thresholds[0]["percent"], 80)
        self.assertEqual(settings.thresholds[1]["percent"], 90)
        self.assertEqual(settings.thresholds[2]["percent"], 100)
        self.assertTrue(settings.thresholds[2]["locked"])

        event_ids = {item["id"] for item in settings.events}
        self.assertIn(BudgetNotificationEventType.BUDGET_NEAR_LIMIT, event_ids)
        self.assertIn(BudgetNotificationEventType.BUDGET_EXCEEDED, event_ids)
        self.assertIn(BudgetNotificationEventType.GOAL_MILESTONE, event_ids)
        self.assertIn(BudgetNotificationEventType.GOAL_REACHED, event_ids)

        channels = {item["id"]: item for item in settings.channels}
        self.assertTrue(channels[BudgetNotificationChannel.IN_APP]["enabled"])
        self.assertTrue(channels[BudgetNotificationChannel.IN_APP]["deliveryOk"])
        self.assertFalse(channels[BudgetNotificationChannel.EMAIL]["enabled"])
        self.assertFalse(channels[BudgetNotificationChannel.EMAIL]["deliveryOk"])
        self.assertFalse(channels[BudgetNotificationChannel.PUSH]["enabled"])
        self.assertFalse(channels[BudgetNotificationChannel.PUSH]["deliveryOk"])

        self.assertEqual(settings.anti_spam["minRepeatHours"], 24)
        self.assertTrue(settings.anti_spam["groupNotifications"])
        self.assertEqual(settings.anti_spam["cooldownMinutes"], 15)

        self.assertEqual(settings.goals["milestonePercents"], [25, 50, 75, 100])
        self.assertFalse(settings.goals["notifyOnLag"])
        self.assertEqual(settings.goals["lagDays"], 7)
        self.assertEqual(settings.goals["selectedGoalIds"], [])

    def test_thresholds_must_be_unique_and_ascending(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            thresholds=[
                {
                    "id": "near_limit",
                    "label": "Приближение",
                    "hint": "",
                    "percent": 90,
                    "active": True,
                    "locked": False,
                },
                {
                    "id": "warning",
                    "label": "Предупреждение",
                    "hint": "",
                    "percent": 80,
                    "active": True,
                    "locked": False,
                },
            ],
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("thresholds", context.exception.message_dict)

    def test_threshold_percent_must_be_in_allowed_range(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            thresholds=[
                {
                    "id": "near_limit",
                    "label": "Приближение",
                    "hint": "",
                    "percent": 0,
                    "active": True,
                    "locked": False,
                },
            ],
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("thresholds.near_limit.percent", context.exception.message_dict)

    def test_critical_threshold_must_remain_100_percent(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            thresholds=[
                {
                    "id": "critical",
                    "label": "Критический",
                    "hint": "",
                    "percent": 95,
                    "active": True,
                    "locked": True,
                },
            ],
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("thresholds.critical.percent", context.exception.message_dict)

    def test_event_group_must_match_event_type(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            events=[
                {
                    "id": BudgetNotificationEventType.BUDGET_EXCEEDED,
                    "group": "goal",
                    "label": "Бюджет превышен",
                    "icon": "alert-circle",
                    "iconTone": "error",
                    "enabled": True,
                },
            ],
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("events.budget_exceeded.group", context.exception.message_dict)

    def test_unknown_channel_is_rejected(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            channels=[
                {
                    "id": "telegram",
                    "label": "Telegram",
                    "description": "",
                    "icon": "send",
                    "enabled": True,
                    "deliveryHint": "",
                    "deliveryOk": False,
                },
            ],
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("channels.telegram.id", context.exception.message_dict)

    def test_anti_spam_values_are_limited(self):
        settings = BudgetNotificationSettings(
            user=self.user,
            anti_spam={
                "minRepeatHours": 0,
                "groupNotifications": True,
                "cooldownMinutes": 2000,
            },
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("antiSpam.minRepeatHours", context.exception.message_dict)
        self.assertIn("antiSpam.cooldownMinutes", context.exception.message_dict)

    def test_selected_goal_ids_must_belong_to_user(self):
        own_goal = Goal.objects.create(
            user=self.user,
            name="Отпуск",
            category=GoalCategory.TRAVEL,
            priority=GoalPriority.MEDIUM,
            target_amount=Decimal("150000.00"),
            current_amount=Decimal("75000.00"),
        )
        other_goal = Goal.objects.create(
            user=self.other_user,
            name="Чужая цель",
            category=GoalCategory.SAVINGS,
            priority=GoalPriority.LOW,
            target_amount=Decimal("50000.00"),
            current_amount=Decimal("10000.00"),
        )

        settings = BudgetNotificationSettings(
            user=self.user,
            goals={
                "milestonePercents": [25, 50, 75, 100],
                "milestoneEnabled": {
                    "25": True,
                    "50": True,
                    "75": True,
                    "100": True,
                },
                "notifyOnLag": True,
                "lagDays": 7,
                "selectedGoalIds": [own_goal.id, other_goal.id],
            },
        )

        with self.assertRaises(ValidationError) as context:
            settings.full_clean()

        self.assertIn("goals.selectedGoalIds", context.exception.message_dict)

    def test_selected_goal_ids_are_normalized_to_ints(self):
        goal = Goal.objects.create(
            user=self.user,
            name="Подушка",
            category=GoalCategory.SAVINGS,
            priority=GoalPriority.HIGH,
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("25000.00"),
        )
        settings = BudgetNotificationSettings(
            user=self.user,
            goals={
                "milestonePercents": [25, 50],
                "milestoneEnabled": {
                    "25": True,
                    "50": False,
                },
                "notifyOnLag": False,
                "lagDays": 3,
                "selectedGoalIds": [str(goal.id)],
            },
        )

        settings.full_clean()

        self.assertEqual(settings.goals["selectedGoalIds"], [goal.id])
        self.assertEqual(settings.goals["milestonePercents"], [25, 50])
        self.assertEqual(
            settings.goals["milestoneEnabled"],
            {
                "25": True,
                "50": False,
            },
        )
