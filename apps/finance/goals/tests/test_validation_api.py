from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import (
    Goal,
    GoalCategory,
    GoalContribution,
    GoalPriority,
    GoalStatus,
)
from apps.finance.testing import FinanceAPITestCase


class FinanceGoalValidationAPITests(FinanceAPITestCase):
    def create_goal(
        self,
        *,
        name="Ремонт",
        target_amount="100000.00",
        current_amount="0.00",
        status_value=GoalStatus.ACTIVE,
        deadline=None,
        account=None,
    ):
        return Goal.objects.create(
            user=self.user,
            account=account if account is not None else self.account,
            name=name,
            category=GoalCategory.HOUSING,
            priority=GoalPriority.MEDIUM,
            status=status_value,
            target_amount=Decimal(target_amount),
            current_amount=Decimal(current_amount),
            deadline=deadline or (self.today + timedelta(days=30)),
        )

    def post_topup(self, goal, *, amount="1000.00", account=None, date=None):
        return self.client.post(
            reverse("finance:goal-topups", kwargs={"pk": goal.id}),
            data={
                "amountRub": amount,
                "date": str(date or self.today),
                "accountId": (account or self.account).id,
            },
            format="json",
        )

    def get_error_code(self, response):
        return response.data.get("error", {}).get("code")

    def test_create_goal_with_past_deadline_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Просроченная цель",
                "targetRub": "100000.00",
                "deadline": str(self.today - timedelta(days=1)),
                "categoryKey": GoalCategory.SAVINGS,
                "priority": GoalPriority.MEDIUM,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_goal_with_zero_target_amount_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Нулевая цель",
                "targetRub": "0.00",
                "deadline": str(self.today + timedelta(days=30)),
                "categoryKey": GoalCategory.SAVINGS,
                "priority": GoalPriority.MEDIUM,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_goal_duplicate_name_returns_bad_request(self):
        self.authenticate()
        self.create_goal(name="Отпуск")

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "отпуск",
                "targetRub": "100000.00",
                "deadline": str(self.today + timedelta(days=30)),
                "categoryKey": GoalCategory.TRAVEL,
                "priority": GoalPriority.HIGH,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_goal_cannot_change_current_amount_directly(self):
        self.authenticate()
        goal = self.create_goal(name="Цель")

        response = self.client.patch(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
            data={"currentRub": "50000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("0.00"))

    def test_patch_goal_target_less_than_current_amount_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(
            name="Почти закрытая цель",
            target_amount="100000.00",
            current_amount="80000.00",
        )

        response = self.client.patch(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
            data={"targetRub": "70000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_goal_with_other_user_account_returns_bad_request(self):
        self.authenticate()

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Цель с чужим счётом",
                "targetRub": "100000.00",
                "deadline": str(self.today + timedelta(days=30)),
                "categoryKey": GoalCategory.SAVINGS,
                "priority": GoalPriority.MEDIUM,
                "accountId": self.other_account.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_goal_with_archived_account_returns_bad_request(self):
        self.authenticate()
        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Цель с архивным счётом",
                "targetRub": "100000.00",
                "deadline": str(self.today + timedelta(days=30)),
                "categoryKey": GoalCategory.SAVINGS,
                "priority": GoalPriority.MEDIUM,
                "accountId": self.cash_account.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_restore_goal_with_past_deadline_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(
            name="Старая архивная цель",
            status_value=GoalStatus.ARCHIVED,
            deadline=self.today - timedelta(days=1),
        )

        response = self.client.patch(
            reverse("finance:goal-restore", kwargs={"pk": goal.id}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.ARCHIVED)

    def test_topup_completed_goal_returns_conflict(self):
        self.authenticate()
        goal = self.create_goal(
            name="Завершённая цель",
            status_value=GoalStatus.COMPLETED,
            target_amount="100000.00",
            current_amount="100000.00",
        )

        response = self.post_topup(goal, amount="1000.00")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.get_error_code(response), "goal_not_active")

    def test_topup_archived_goal_returns_conflict(self):
        self.authenticate()
        goal = self.create_goal(
            name="Архивная цель",
            status_value=GoalStatus.ARCHIVED,
        )

        response = self.post_topup(goal, amount="1000.00")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.get_error_code(response), "goal_not_active")

    def test_topup_cancelled_goal_returns_conflict(self):
        self.authenticate()
        goal = self.create_goal(
            name="Отменённая цель",
            status_value=GoalStatus.CANCELLED,
        )

        response = self.post_topup(goal, amount="1000.00")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.get_error_code(response), "goal_not_active")

    def test_topup_exceeding_remaining_amount_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(
            name="Почти завершённая цель",
            target_amount="10000.00",
            current_amount="9000.00",
        )

        response = self.post_topup(goal, amount="2000.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topup_future_date_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(name="Цель")

        response = self.post_topup(
            goal,
            amount="1000.00",
            date=self.today + timedelta(days=1),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topup_with_insufficient_account_balance_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(
            name="Большая цель",
            target_amount="20000.00",
            current_amount="0.00",
        )

        response = self.post_topup(goal, amount="15000.00")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_topup_with_archived_account_returns_bad_request(self):
        self.authenticate()
        goal = self.create_goal(name="Цель")
        self.cash_account.is_archived = True
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.post_topup(goal, amount="1000.00", account=self.cash_account)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_goal_with_topups_returns_conflict(self):
        self.authenticate()
        goal = self.create_goal(name="Цель с пополнением")
        GoalContribution.objects.create(
            user=self.user,
            goal=goal,
            account=self.account,
            account_name=self.account.name,
            amount=Decimal("1000.00"),
            contribution_date=self.today,
        )

        response = self.client.delete(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.get_error_code(response), "goal_has_topups")
        self.assertTrue(Goal.objects.filter(pk=goal.id).exists())
