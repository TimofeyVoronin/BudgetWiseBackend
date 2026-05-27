from datetime import timedelta
from decimal import Decimal

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.finance.currencies.services import ensure_user_currencies, get_user_currency_by_code
from apps.finance.models import Account, Goal, GoalCategory, GoalPriority, GoalStatus
from apps.finance.testing import FinanceAPITestCase


@override_settings(CURRENCY_RATES_ENABLED=False)
class FinanceGoalsAPITests(FinanceAPITestCase):
    def create_goal(
        self,
        *,
        user=None,
        account=None,
        name="Ремонт",
        category=GoalCategory.HOUSING,
        priority=GoalPriority.MEDIUM,
        status_value=GoalStatus.ACTIVE,
        target_amount="100000.00",
        current_amount="0.00",
        deadline=None,
        comment="",
    ):
        return Goal.objects.create(
            user=user or self.user,
            account=account if account is not None else self.account,
            name=name,
            category=category,
            priority=priority,
            status=status_value,
            target_amount=Decimal(target_amount),
            current_amount=Decimal(current_amount),
            deadline=deadline or (self.today + timedelta(days=30)),
            comment=comment,
        )

    def get_goal_ids(self, response):
        return [item["id"] for item in response.data["results"]]

    def create_usd_account(self):
        ensure_user_currencies(self.user)
        usd_currency = get_user_currency_by_code(self.user, "USD")
        usd_currency.is_visible = True
        usd_currency.rate_to_primary = Decimal("100.00000000")
        usd_currency.save(update_fields=["is_visible", "rate_to_primary", "updated_at"])

        return Account.objects.create(
            user=self.user,
            name="USD card",
            initial_balance=Decimal("1000.00"),
            balance=Decimal("1000.00"),
            currency="USD",
        )

    def test_goal_list_requires_authentication(self):
        response = self.client.get(reverse("finance:goal-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_goal_list_returns_only_current_user_goals(self):
        self.authenticate()
        own_goal = self.create_goal(name="Моя цель")
        other_goal = self.create_goal(
            user=self.other_user,
            account=self.other_account,
            name="Чужая цель",
        )

        response = self.client.get(reverse("finance:goal-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertIn(own_goal.id, goal_ids)
        self.assertNotIn(other_goal.id, goal_ids)

    def test_goal_list_returns_active_goals_by_default(self):
        self.authenticate()
        active_goal = self.create_goal(name="Активная цель")
        completed_goal = self.create_goal(
            name="Завершённая цель",
            status_value=GoalStatus.COMPLETED,
            current_amount="100000.00",
        )
        archived_goal = self.create_goal(
            name="Архивная цель",
            status_value=GoalStatus.ARCHIVED,
        )
        cancelled_goal = self.create_goal(
            name="Отменённая цель",
            status_value=GoalStatus.CANCELLED,
        )

        response = self.client.get(reverse("finance:goal-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertIn(active_goal.id, goal_ids)
        self.assertNotIn(completed_goal.id, goal_ids)
        self.assertNotIn(archived_goal.id, goal_ids)
        self.assertNotIn(cancelled_goal.id, goal_ids)

    def test_goal_list_filters_by_status(self):
        self.authenticate()
        active_goal = self.create_goal(name="Активная цель")
        completed_goal = self.create_goal(
            name="Завершённая цель",
            status_value=GoalStatus.COMPLETED,
            current_amount="100000.00",
        )

        response = self.client.get(
            reverse("finance:goal-list"),
            data={"status": GoalStatus.COMPLETED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertIn(completed_goal.id, goal_ids)
        self.assertNotIn(active_goal.id, goal_ids)

    def test_goal_list_status_all_returns_all_user_goals(self):
        self.authenticate()
        active_goal = self.create_goal(name="Активная цель")
        archived_goal = self.create_goal(
            name="Архивная цель",
            status_value=GoalStatus.ARCHIVED,
        )

        response = self.client.get(
            reverse("finance:goal-list"),
            data={"status": "all"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertIn(active_goal.id, goal_ids)
        self.assertIn(archived_goal.id, goal_ids)

    def test_goal_list_searches_by_name_and_comment(self):
        self.authenticate()
        target_goal = self.create_goal(
            name="Поездка в Японию",
            category=GoalCategory.TRAVEL,
            comment="важная поездка",
        )
        self.create_goal(name="Ремонт")

        response = self.client.get(
            reverse("finance:goal-list"),
            data={"search": "Японию"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertEqual(goal_ids, [target_goal.id])

    def test_goal_list_sorts_by_progress(self):
        self.authenticate()
        low_progress = self.create_goal(
            name="Автомобиль",
            current_amount="10000.00",
            target_amount="100000.00",
        )
        high_progress = self.create_goal(
            name="Ноутбук",
            current_amount="80000.00",
            target_amount="100000.00",
        )

        response = self.client.get(
            reverse("finance:goal-list"),
            data={"sortBy": "progress", "sortDir": "desc"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal_ids = self.get_goal_ids(response)
        self.assertLess(goal_ids.index(high_progress.id), goal_ids.index(low_progress.id))

    def test_create_goal_success(self):
        self.authenticate()
        response = self.client.post(
            reverse("finance:goal-list"),
            data={
                "name": "Отпуск",
                "targetRub": "250000.00",
                "deadline": str(self.today + timedelta(days=120)),
                "categoryKey": GoalCategory.TRAVEL,
                "priority": GoalPriority.HIGH,
                "accountId": self.account.id,
                "comment": "Семейный отпуск",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Отпуск")
        self.assertEqual(response.data["targetRub"], "250000.00")
        self.assertEqual(response.data["currentRub"], "0.00")
        self.assertEqual(response.data["categoryKey"], GoalCategory.TRAVEL)
        self.assertEqual(response.data["priority"], GoalPriority.HIGH)
        self.assertEqual(response.data["accountId"], self.account.id)

    def test_retrieve_goal_returns_goal_and_history(self):
        self.authenticate()
        goal = self.create_goal(name="Финансовая подушка")

        response = self.client.get(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("goal", response.data)
        self.assertIn("history", response.data)
        self.assertEqual(response.data["goal"]["id"], goal.id)
        self.assertEqual(response.data["history"], [])

    def test_patch_goal_success(self):
        self.authenticate()
        goal = self.create_goal(name="Старая цель")

        response = self.client.patch(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
            data={
                "name": "Новая цель",
                "priority": GoalPriority.HIGH,
                "targetRub": "120000.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        goal.refresh_from_db()
        self.assertEqual(goal.name, "Новая цель")
        self.assertEqual(goal.priority, GoalPriority.HIGH)
        self.assertEqual(goal.target_amount, Decimal("120000.00"))

    def test_goal_summary_counts_active_and_completed_goals(self):
        self.authenticate()
        self.create_goal(
            name="Активная цель 1",
            target_amount="100000.00",
            current_amount="30000.00",
        )
        self.create_goal(
            name="Активная цель 2",
            target_amount="200000.00",
            current_amount="50000.00",
        )
        self.create_goal(
            name="Завершённая цель",
            status_value=GoalStatus.COMPLETED,
            target_amount="100000.00",
            current_amount="100000.00",
        )

        response = self.client.get(reverse("finance:goal-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalCurrentRub"], "80000.00")
        self.assertEqual(response.data["totalTargetRub"], "300000.00")
        self.assertEqual(response.data["active_count"], 2)
        self.assertEqual(response.data["completed_count"], 1)


    def test_goal_list_converts_amounts_to_display_currency(self):
        self.authenticate()
        usd_account = self.create_usd_account()
        goal = self.create_goal(
            account=usd_account,
            target_amount="1000.00",
            current_amount="250.00",
        )

        response = self.client.get(
            reverse("finance:goal-list"),
            data={"currency": "RUB"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data["results"] if item["id"] == goal.id)
        self.assertEqual(row["sourceCurrency"], "USD")
        self.assertEqual(row["targetRub"], "100000.00")
        self.assertEqual(row["currentRub"], "25000.00")
        self.assertEqual(row["target"], {"amount": 100000.0, "currency": "RUB"})
        self.assertEqual(row["current"], {"amount": 25000.0, "currency": "RUB"})

    def test_goal_summary_converts_mixed_goal_currencies(self):
        self.authenticate()
        usd_account = self.create_usd_account()
        self.create_goal(
            account=usd_account,
            name="USD goal",
            target_amount="100.00",
            current_amount="10.00",
        )
        self.create_goal(
            account=self.account,
            name="RUB goal",
            target_amount="1000.00",
            current_amount="500.00",
        )

        response = self.client.get(
            reverse("finance:goal-summary"),
            data={"currency": "RUB"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["totalCurrentRub"], "1500.00")
        self.assertEqual(response.data["totalTargetRub"], "11000.00")
        self.assertEqual(response.data["totalCurrent"], {"amount": 1500.0, "currency": "RUB"})
        self.assertEqual(response.data["totalTarget"], {"amount": 11000.0, "currency": "RUB"})
        self.assertEqual(response.data["currency"], "RUB")
        self.assertEqual(response.data["currencyContext"]["code"], "RUB")

    def test_goal_meta_returns_form_options(self):
        self.authenticate()

        response = self.client.get(reverse("finance:goal-meta"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("categories", response.data)
        self.assertIn("priorities", response.data)
        self.assertIn("statuses", response.data)
        self.assertTrue(response.data["categories"])
        self.assertTrue(response.data["priorities"])
        self.assertTrue(response.data["statuses"])

    def test_archive_restore_complete_and_cancel_goal_success(self):
        self.authenticate()
        goal = self.create_goal(name="Цель со статусами")

        archive_response = self.client.patch(
            reverse("finance:goal-archive", kwargs={"pk": goal.id}),
            format="json",
        )
        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.ARCHIVED)

        restore_response = self.client.patch(
            reverse("finance:goal-restore", kwargs={"pk": goal.id}),
            format="json",
        )
        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.ACTIVE)

        complete_response = self.client.patch(
            reverse("finance:goal-complete", kwargs={"pk": goal.id}),
            format="json",
        )
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.COMPLETED)

        cancel_response = self.client.patch(
            reverse("finance:goal-cancel", kwargs={"pk": goal.id}),
            format="json",
        )
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        goal.refresh_from_db()
        self.assertEqual(goal.status, GoalStatus.CANCELLED)

    def test_delete_goal_without_topups_success(self):
        self.authenticate()
        goal = self.create_goal(name="Удаляемая цель")

        response = self.client.delete(
            reverse("finance:goal-detail", kwargs={"pk": goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Goal.objects.filter(pk=goal.id).exists())

    def test_other_user_goal_returns_not_found(self):
        self.authenticate()
        other_goal = self.create_goal(
            user=self.other_user,
            account=self.other_account,
            name="Чужая цель",
        )

        response = self.client.get(
            reverse("finance:goal-detail", kwargs={"pk": other_goal.id}),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
