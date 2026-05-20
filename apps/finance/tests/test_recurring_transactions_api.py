from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import (
    RecurringChargeStatus,
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    RecurringTransactionCharge,
    TransactionType,
)
from apps.finance.tests.base import FinanceAPITestCase


class FinanceRecurringTransactionsAPITests(FinanceAPITestCase):
    def create_recurring(
        self,
        *,
        user=None,
        account=None,
        category=None,
        name="Интернет",
        type=TransactionType.EXPENSE,
        amount="890.00",
        frequency=RecurringFrequency.MONTHLY,
        start_date=None,
        next_charge_date=None,
        status=RecurringStatus.ACTIVE,
        has_end=False,
        end_date=None,
        day_of_month=15,
        template_id="internet",
        template_name="Интернет и связь",
        last_error_code="",
        last_error_message="",
    ):
        start_date = start_date or self.today
        return RecurringTransaction.objects.create(
            user=user or self.user,
            account=account or self.account,
            category=category or self.expense_category,
            name=name,
            type=type,
            amount=Decimal(amount),
            frequency=frequency,
            day_of_month=day_of_month,
            start_date=start_date,
            has_end=has_end,
            end_date=end_date,
            next_charge_date=next_charge_date or start_date,
            status=status,
            template_id=template_id,
            template_name=template_name,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
        )

    def test_recurring_list_requires_authentication(self):
        response = self.client.get(reverse("finance:recurring-transaction-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_recurring_list_returns_only_current_user_items(self):
        self.authenticate()
        own_recurring = self.create_recurring(name="Netflix")
        self.create_recurring(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужая подписка",
        )

        response = self.client.get(reverse("finance:recurring-transaction-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recurring_ids = [item["id"] for item in response.data["results"]]
        self.assertIn(own_recurring.id, recurring_ids)
        self.assertEqual(len(recurring_ids), 1)

    def test_recurring_crud_flow(self):
        self.authenticate()

        payload = {
            "name": "Облачное хранилище",
            "kind": "expense",
            "amountRub": "149.00",
            "categoryId": self.expense_category.id,
            "accountId": self.account.id,
            "schedule": {
                "frequency": "monthly",
                "dayOfMonth": 3,
                "startDate": self.today.isoformat(),
                "hasEnd": False,
                "endDate": None,
                "templateId": "subscription",
            },
            "comment": "Подписка",
        }

        create_response = self.client.post(
            reverse("finance:recurring-transaction-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        recurring_id = create_response.data["id"]
        self.assertEqual(create_response.data["name"], "Облачное хранилище")
        self.assertEqual(create_response.data["kind"], TransactionType.EXPENSE)
        self.assertEqual(create_response.data["amountRub"], "149.00")
        self.assertEqual(create_response.data["frequency"], RecurringFrequency.MONTHLY)
        self.assertEqual(create_response.data["dayOfMonth"], 3)

        detail_response = self.client.get(
            reverse("finance:recurring-transaction-detail", kwargs={"pk": recurring_id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], recurring_id)

        patch_response = self.client.patch(
            reverse("finance:recurring-transaction-detail", kwargs={"pk": recurring_id}),
            data={
                "name": "Облачное хранилище Pro",
                "amountRub": "199.00",
            },
            format="json",
        )

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["name"], "Облачное хранилище Pro")
        self.assertEqual(patch_response.data["amountRub"], "199.00")

        delete_response = self.client.delete(
            reverse("finance:recurring-transaction-detail", kwargs={"pk": recurring_id})
        )

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data["deleted"], True)
        self.assertFalse(RecurringTransaction.objects.filter(pk=recurring_id).exists())

    def test_recurring_actions_pause_resume_and_complete(self):
        self.authenticate()
        recurring = self.create_recurring()

        pause_response = self.client.post(
            reverse("finance:recurring-transaction-pause", kwargs={"pk": recurring.id})
        )

        self.assertEqual(pause_response.status_code, status.HTTP_200_OK)
        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.PAUSED)

        recurring.last_error_code = "INSUFFICIENT_FUNDS"
        recurring.last_error_message = "Недостаточно средств."
        recurring.save(update_fields=["last_error_code", "last_error_message", "updated_at"])

        resume_response = self.client.post(
            reverse("finance:recurring-transaction-resume", kwargs={"pk": recurring.id})
        )

        self.assertEqual(resume_response.status_code, status.HTTP_200_OK)
        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.ACTIVE)
        self.assertEqual(recurring.last_error_code, "")
        self.assertEqual(recurring.last_error_message, "")

        complete_response = self.client.post(
            reverse("finance:recurring-transaction-complete", kwargs={"pk": recurring.id})
        )

        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.COMPLETED)

    def test_recurring_list_filters(self):
        self.authenticate()
        active = self.create_recurring(
            name="ЖКУ",
            amount="5400.00",
            frequency=RecurringFrequency.MONTHLY,
            category=self.expense_category,
            account=self.account,
        )
        paused = self.create_recurring(
            name="Зарплата",
            type=TransactionType.INCOME,
            amount="100000.00",
            frequency=RecurringFrequency.WEEKLY,
            category=self.income_category,
            account=self.cash_account,
            status=RecurringStatus.PAUSED,
        )
        failed = self.create_recurring(
            name="Netflix",
            amount="599.00",
            frequency=RecurringFrequency.YEARLY,
            category=self.transport_category,
            account=self.cash_account,
            status=RecurringStatus.ERROR,
            last_error_code="INSUFFICIENT_FUNDS",
            last_error_message="Недостаточно средств.",
        )

        list_url = reverse("finance:recurring-transaction-list")

        response = self.client.get(list_url, {"statusTab": "active"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(active.id, ids)
        self.assertIn(failed.id, ids)
        self.assertNotIn(paused.id, ids)

        response = self.client.get(list_url, {"statusTab": "paused"})
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [paused.id])

        response = self.client.get(list_url, {"frequencies": "monthly,yearly"})
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(active.id, ids)
        self.assertIn(failed.id, ids)
        self.assertNotIn(paused.id, ids)

        response = self.client.get(list_url, {"accounts": str(self.account.id)})
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [active.id])

        response = self.client.get(list_url, {"categories": str(self.transport_category.id)})
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [failed.id])

        response = self.client.get(
            list_url,
            {
                "amountMin": "500.00",
                "amountMax": "1000.00",
            },
        )
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(failed.id, ids)
        self.assertNotIn(active.id, ids)
        self.assertNotIn(paused.id, ids)

        response = self.client.get(list_url, {"onlyWithErrors": "true"})
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [failed.id])

        response = self.client.get(list_url, {"search": "ЖКУ"})
        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [active.id])

    def test_recurring_summary_meta_preview_validation_and_history(self):
        self.authenticate()
        recurring = self.create_recurring(
            name="Ипотека",
            amount="32000.00",
            frequency=RecurringFrequency.MONTHLY,
            next_charge_date=self.today + timedelta(days=5),
        )
        self.create_recurring(
            name="Пауза",
            status=RecurringStatus.PAUSED,
            next_charge_date=self.today + timedelta(days=10),
        )
        RecurringTransactionCharge.objects.create(
            user=self.user,
            recurring_transaction=recurring,
            scheduled_date=self.today,
            amount=Decimal("32000.00"),
            status=RecurringChargeStatus.SUCCESS,
        )

        summary_response = self.client.get(
            reverse("finance:recurring-transaction-summary")
        )
        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        self.assertEqual(summary_response.data["activeCount"], 1)
        self.assertEqual(summary_response.data["pausedCount"], 1)
        self.assertEqual(summary_response.data["failedCount"], 0)
        self.assertEqual(
            summary_response.data["nextChargeDate"],
            (self.today + timedelta(days=5)).isoformat(),
        )

        meta_response = self.client.get(reverse("finance:recurring-transaction-meta"))
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertIn("frequencies", meta_response.data)
        self.assertIn("accounts", meta_response.data)
        self.assertIn("categories", meta_response.data)
        self.assertIn("templates", meta_response.data)

        preview_response = self.client.post(
            reverse("finance:recurring-transaction-schedule-preview"),
            data={
                "frequency": "monthly",
                "startDate": "2026-01-31",
                "dayOfMonth": 31,
                "count": 3,
            },
            format="json",
        )
        self.assertEqual(preview_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            preview_response.data["dates"],
            ["2026-01-31", "2026-02-28", "2026-03-31"],
        )

        validation_response = self.client.post(
            reverse("finance:recurring-transaction-validate-schedule"),
            data={
                "frequency": "monthly",
                "startDate": "2026-05-20",
                "hasEnd": True,
                "endDate": "2026-05-10",
            },
            format="json",
        )
        self.assertEqual(validation_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validation_response.data["ok"], False)
        self.assertIn("endDate", validation_response.data["fieldErrors"])

        history_response = self.client.get(
            reverse(
                "finance:recurring-transaction-charge-history",
                kwargs={"pk": recurring.id},
            )
        )
        self.assertEqual(history_response.status_code, status.HTTP_200_OK)
        self.assertEqual(history_response.data["recurringId"], recurring.id)
        self.assertEqual(len(history_response.data["items"]), 1)

    def test_recurring_validation_errors(self):
        self.authenticate()
        list_url = reverse("finance:recurring-transaction-list")

        response = self.client.get(list_url, {"statusTab": "wrong"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"frequencies": "monthly,wrong"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"accounts": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            list_url,
            {
                "amountMin": "1000.00",
                "amountMax": "100.00",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"onlyWithErrors": "maybe"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"search": "x" * 101})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            reverse(
                "finance:recurring-transaction-charge-history",
                kwargs={"pk": self.create_recurring().id},
            ),
            {"limit": 0},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recurring_cannot_use_foreign_account_or_category(self):
        self.authenticate()

        payload = {
            "name": "Чужая операция",
            "kind": "expense",
            "amountRub": "100.00",
            "categoryId": self.expense_category.id,
            "accountId": self.other_account.id,
            "schedule": {
                "frequency": "monthly",
                "startDate": self.today.isoformat(),
                "hasEnd": False,
            },
        }

        response = self.client.post(
            reverse("finance:recurring-transaction-list"),
            data=payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
