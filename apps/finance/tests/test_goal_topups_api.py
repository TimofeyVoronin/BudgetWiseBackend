from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.goals import GOAL_TOPUP_CATEGORY_NAME
from apps.finance.models import (
    Category,
    Goal,
    GoalCategory,
    GoalContribution,
    GoalPriority,
    GoalStatus,
    Transaction,
    TransactionType,
)
from apps.finance.tests.base import FinanceAPITestCase


class FinanceGoalTopupsAPITests(FinanceAPITestCase):
    def create_goal(
        self,
        *,
        name="Ремонт",
        target_amount="100000.00",
        current_amount="0.00",
        status_value=GoalStatus.ACTIVE,
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
            deadline=self.today + timedelta(days=30),
        )

    def post_topup(self, goal, *, amount="1000.00", account=None, date=None, comment=""):
        return self.client.post(
            reverse("finance:goal-topups", kwargs={"pk": goal.id}),
            data={
                "amountRub": amount,
                "date": str(date or self.today),
                "accountId": (account or self.account).id,
                "comment": comment,
            },
            format="json",
        )

    def test_goal_topups_list_requires_authentication(self):
        goal = self.create_goal()

        response = self.client.get(
            reverse("finance:goal-topups", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_goal_topups_list_returns_goal_history(self):
        self.authenticate()
        goal = self.create_goal(name="Финансовая подушка")
        contribution = GoalContribution.objects.create(
            user=self.user,
            goal=goal,
            account=self.account,
            account_name=self.account.name,
            amount=Decimal("1500.00"),
            contribution_date=self.today,
            comment="Первое пополнение",
        )

        response = self.client.get(
            reverse("finance:goal-topups", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], contribution.id)
        self.assertEqual(response.data["results"][0]["amountRub"], "1500.00")
        self.assertEqual(response.data["results"][0]["accountName"], self.account.name)

    def test_goal_topup_increases_current_amount_and_creates_history(self):
        self.authenticate()
        goal = self.create_goal(target_amount="100000.00", current_amount="10000.00")

        response = self.post_topup(goal, amount="5000.00", comment="Пополнение")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("15000.00"))
        self.assertEqual(GoalContribution.objects.filter(goal=goal).count(), 1)
        contribution = GoalContribution.objects.get(goal=goal)
        self.assertEqual(contribution.amount, Decimal("5000.00"))
        self.assertEqual(contribution.account, self.account)
        self.assertEqual(contribution.account_name, self.account.name)
        self.assertEqual(contribution.comment, "Пополнение")

    def test_goal_topup_creates_transaction_and_decreases_account_balance(self):
        self.authenticate()
        goal = self.create_goal(target_amount="100000.00", current_amount="0.00")
        initial_balance = self.account.balance

        response = self.post_topup(goal, amount="2500.00")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, initial_balance - Decimal("2500.00"))

        transaction = Transaction.objects.get(pk=response.data["operationId"])
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.account, self.account)
        self.assertEqual(transaction.type, TransactionType.EXPENSE)
        self.assertEqual(transaction.amount, Decimal("2500.00"))
        self.assertIn(goal.name, transaction.description)

        contribution = GoalContribution.objects.get(goal=goal)
        self.assertEqual(contribution.transaction, transaction)

    def test_goal_topup_creates_or_reuses_goal_topup_category(self):
        self.authenticate()
        goal = self.create_goal(target_amount="100000.00")

        response = self.post_topup(goal, amount="1000.00")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        category = Category.objects.get(
            user=self.user,
            name=GOAL_TOPUP_CATEGORY_NAME,
            type=TransactionType.EXPENSE,
        )
        transaction = Transaction.objects.get(pk=response.data["operationId"])
        self.assertEqual(transaction.category, category)

    def test_goal_topup_completes_goal_when_target_is_reached(self):
        self.authenticate()
        goal = self.create_goal(target_amount="10000.00", current_amount="9000.00")

        response = self.post_topup(goal, amount="1000.00")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        goal.refresh_from_db()
        self.assertEqual(goal.current_amount, Decimal("10000.00"))
        self.assertEqual(goal.status, GoalStatus.COMPLETED)

    def test_goal_detail_includes_topup_history(self):
        self.authenticate()
        goal = self.create_goal(target_amount="100000.00")
        topup_response = self.post_topup(goal, amount="1000.00")
        self.assertEqual(topup_response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["history"]), 1)
        self.assertEqual(response.data["history"][0]["amountRub"], "1000.00")
        self.assertEqual(response.data["history"][0]["accountName"], self.account.name)
        self.assertEqual(response.data["history"][0]["operationId"], topup_response.data["operationId"])

    def test_goal_topups_for_other_user_goal_return_not_found(self):
        self.authenticate()
        other_goal = Goal.objects.create(
            user=self.other_user,
            account=self.other_account,
            name="Чужая цель",
            category=GoalCategory.OTHER,
            priority=GoalPriority.LOW,
            status=GoalStatus.ACTIVE,
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("0.00"),
            deadline=self.today + timedelta(days=30),
        )

        response = self.client.get(
            reverse("finance:goal-topups", kwargs={"pk": other_goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
