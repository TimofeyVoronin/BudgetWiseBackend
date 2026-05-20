from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status

from apps.finance.models import (
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)
from apps.finance.tests.base import FinanceAPITestCase


class FinancePlannedTransactionsAPITests(FinanceAPITestCase):
    def create_planned(
        self,
        *,
        user=None,
        account=None,
        category=None,
        name="Плановая операция",
        type=TransactionType.EXPENSE,
        amount="100.00",
        planned_date=None,
        status=PlannedStatus.PENDING,
        include_in_forecast=True,
        comment="",
        last_error_code="",
        last_error_message="",
    ):
        return PlannedTransaction.objects.create(
            user=user or self.user,
            account=account or self.account,
            category=category or self.expense_category,
            name=name,
            type=type,
            amount=Decimal(amount),
            planned_date=planned_date or self.today,
            status=status,
            include_in_forecast=include_in_forecast,
            comment=comment,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
        )

    def get_planned_ids(self, response):
        return [item["id"] for item in response.data["results"]]

    def test_planned_transactions_list_requires_authentication(self):
        response = self.client.get(reverse("finance:planned-transaction-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_planned_transactions_list_returns_only_current_user_items(self):
        self.authenticate()
        own_planned = self.create_planned(name="Мой план")
        self.create_planned(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            name="Чужой план",
        )

        response = self.client.get(reverse("finance:planned-transaction-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_planned_ids(response), [own_planned.id])

    def test_planned_transaction_crud_flow(self):
        self.authenticate()
        planned_date = self.today + timedelta(days=10)

        create_response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Такси в аэропорт",
                "kind": TransactionType.EXPENSE,
                "amountRub": "1250.00",
                "categoryId": self.transport_category.id,
                "accountId": self.account.id,
                "plannedDate": planned_date.isoformat(),
                "includeInForecast": True,
                "comment": "Будущая поездка",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        planned_id = create_response.data["id"]
        self.assertEqual(create_response.data["name"], "Такси в аэропорт")
        self.assertEqual(create_response.data["kind"], TransactionType.EXPENSE)
        self.assertEqual(create_response.data["amountRub"], "1250.00")
        self.assertEqual(create_response.data["categoryId"], self.transport_category.id)
        self.assertEqual(create_response.data["accountId"], self.account.id)
        self.assertEqual(create_response.data["plannedDate"], planned_date.isoformat())

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("10000.00"))
        self.assertEqual(Transaction.objects.count(), 0)

        detail_response = self.client.get(
            reverse("finance:planned-transaction-detail", kwargs={"pk": planned_id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], planned_id)

        patch_response = self.client.patch(
            reverse("finance:planned-transaction-detail", kwargs={"pk": planned_id}),
            data={
                "name": "Такси в аэропорт, обновлено",
                "amountRub": "1500.00",
            },
            format="json",
        )

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["name"], "Такси в аэропорт, обновлено")
        self.assertEqual(patch_response.data["amountRub"], "1500.00")

        delete_response = self.client.delete(
            reverse("finance:planned-transaction-detail", kwargs={"pk": planned_id})
        )

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(delete_response.data["deleted"], True)
        self.assertEqual(delete_response.data["id"], planned_id)
        self.assertFalse(PlannedTransaction.objects.filter(pk=planned_id).exists())

    def test_planned_transaction_status_actions(self):
        self.authenticate()
        planned = self.create_planned(
            status=PlannedStatus.PENDING,
            last_error_code="INSUFFICIENT_FUNDS",
            last_error_message="Недостаточно средств.",
        )

        confirm_response = self.client.post(
            reverse("finance:planned-transaction-confirm", kwargs={"pk": planned.id})
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        planned.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.CONFIRMED)
        self.assertEqual(planned.last_error_code, "")
        self.assertEqual(planned.last_error_message, "")

        cancel_response = self.client.post(
            reverse("finance:planned-transaction-cancel", kwargs={"pk": planned.id})
        )

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        planned.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.CANCELLED)

        restore_response = self.client.post(
            reverse("finance:planned-transaction-restore", kwargs={"pk": planned.id})
        )

        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)
        planned.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.PENDING)

    def test_planned_transaction_convert_action_creates_transaction_and_updates_balance(self):
        self.authenticate()
        planned = self.create_planned(
            name="Оплата интернета",
            amount="890.00",
            planned_date=self.today,
            comment="Домашний интернет",
        )

        response = self.client.post(
            reverse("finance:planned-transaction-convert", kwargs={"pk": planned.id}),
            data={
                "operationDate": self.today.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["operationId"])

        planned.refresh_from_db()
        self.account.refresh_from_db()
        transaction = Transaction.objects.get(pk=response.data["operationId"])

        self.assertEqual(planned.status, PlannedStatus.CONVERTED)
        self.assertEqual(planned.converted_transaction, transaction)
        self.assertIsNotNone(planned.converted_at)
        self.assertEqual(transaction.description, "Домашний интернет")
        self.assertEqual(transaction.operation_date, self.today)
        self.assertEqual(self.account.balance, Decimal("9110.00"))

        second_response = self.client.post(
            reverse("finance:planned-transaction-convert", kwargs={"pk": planned.id}),
            data={
                "operationDate": self.today.isoformat(),
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(second_response.data["operationId"], transaction.id)

    def test_planned_transaction_convert_rejects_cancelled_item(self):
        self.authenticate()
        planned = self.create_planned(status=PlannedStatus.CANCELLED)

        response = self.client.post(
            reverse("finance:planned-transaction-convert", kwargs={"pk": planned.id}),
            data={
                "operationDate": self.today.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Transaction.objects.count(), 0)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("10000.00"))

    def test_planned_transactions_list_filters(self):
        self.authenticate()
        taxi = self.create_planned(
            name="Такси",
            category=self.transport_category,
            account=self.account,
            amount="800.00",
            planned_date=self.today + timedelta(days=1),
            status=PlannedStatus.PENDING,
        )
        salary = self.create_planned(
            name="Зарплата",
            type=TransactionType.INCOME,
            category=self.income_category,
            account=self.cash_account,
            amount="70000.00",
            planned_date=self.today + timedelta(days=5),
            status=PlannedStatus.CONFIRMED,
        )
        cancelled = self.create_planned(
            name="Отмененная покупка",
            amount="1500.00",
            planned_date=self.today + timedelta(days=20),
            status=PlannedStatus.CANCELLED,
        )

        list_url = reverse("finance:planned-transaction-list")

        response = self.client.get(list_url, {"statusTab": "pending"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_planned_ids(response), [taxi.id])

        response = self.client.get(list_url, {"statuses": "confirmed,cancelled"})
        ids = self.get_planned_ids(response)
        self.assertIn(salary.id, ids)
        self.assertIn(cancelled.id, ids)
        self.assertNotIn(taxi.id, ids)

        response = self.client.get(list_url, {"accounts": str(self.cash_account.id)})
        self.assertEqual(self.get_planned_ids(response), [salary.id])

        response = self.client.get(list_url, {"categories": str(self.transport_category.id)})
        self.assertEqual(self.get_planned_ids(response), [taxi.id])

        response = self.client.get(
            list_url,
            {
                "amountMin": "700.00",
                "amountMax": "900.00",
            },
        )
        self.assertEqual(self.get_planned_ids(response), [taxi.id])

        response = self.client.get(list_url, {"search": "зарп"})
        self.assertEqual(self.get_planned_ids(response), [salary.id])

        response = self.client.get(
            list_url,
            {
                "dateFrom": (self.today + timedelta(days=2)).isoformat(),
                "dateTo": (self.today + timedelta(days=10)).isoformat(),
            },
        )
        self.assertEqual(self.get_planned_ids(response), [salary.id])

    def test_planned_transactions_duplicate_filter_and_duplicate_checker(self):
        self.authenticate()
        planned_date = self.today + timedelta(days=3)
        first = self.create_planned(
            name="Аренда",
            amount="25000.00",
            planned_date=planned_date,
        )
        second = self.create_planned(
            name="Аренда",
            amount="25000.00",
            planned_date=planned_date,
        )
        self.create_planned(
            name="Обычный план",
            amount="500.00",
            planned_date=planned_date,
        )

        response = self.client.get(
            reverse("finance:planned-transaction-list"),
            {
                "onlyDuplicates": "true",
                "page_size": 20,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(self.get_planned_ids(response)), {first.id, second.id})

        duplicate_response = self.client.post(
            reverse("finance:planned-transaction-check-duplicate"),
            data={
                "name": "Аренда",
                "plannedDate": planned_date.isoformat(),
                "categoryId": self.expense_category.id,
                "accountId": self.account.id,
                "amountRub": "25000.00",
            },
            format="json",
        )

        self.assertEqual(duplicate_response.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate_response.data["isDuplicate"], True)
        self.assertEqual(
            duplicate_response.data["message"],
            "Похожая планируемая операция уже существует.",
        )

    def test_planned_summary_meta_calendar_validation_and_forecast(self):
        self.authenticate()
        planned = self.create_planned(
            name="Страховка",
            amount="3000.00",
            planned_date=self.today,
            status=PlannedStatus.PENDING,
        )
        self.create_planned(
            name="Будущая зарплата",
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="10000.00",
            planned_date=self.today + timedelta(days=7),
            status=PlannedStatus.CONFIRMED,
        )

        summary_response = self.client.get(
            reverse("finance:planned-transaction-summary")
        )
        self.assertEqual(summary_response.status_code, status.HTTP_200_OK)
        self.assertIn("plannedMonthRub", summary_response.data)
        self.assertGreaterEqual(summary_response.data["toConfirmCount"], 1)

        meta_response = self.client.get(reverse("finance:planned-transaction-meta"))
        self.assertEqual(meta_response.status_code, status.HTTP_200_OK)
        self.assertIn("accounts", meta_response.data)
        self.assertIn("categories", meta_response.data)
        self.assertIn("statuses", meta_response.data)

        calendar_response = self.client.get(
            reverse("finance:planned-transaction-calendar"),
            {
                "year": planned.planned_date.year,
                "month": planned.planned_date.month,
            },
        )
        self.assertEqual(calendar_response.status_code, status.HTTP_200_OK)
        badges = [
            badge
            for cell in calendar_response.data["cells"]
            for badge in cell["badges"]
        ]
        self.assertIn(str(planned.id), [badge["id"] for badge in badges])

        validation_response = self.client.post(
            reverse("finance:planned-transaction-validate-form"),
            data={
                "name": "Проверка даты",
                "kind": TransactionType.EXPENSE,
                "amountAbs": "100.00",
                "plannedDate": (self.today - timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(validation_response.status_code, status.HTTP_200_OK)
        self.assertEqual(validation_response.data["ok"], False)
        self.assertIn("plannedDate", validation_response.data["fieldErrors"])

        forecast_response = self.client.get(
            reverse("finance:planned-transaction-forecast"),
            {
                "dateFrom": self.today.isoformat(),
                "dateTo": (self.today + timedelta(days=7)).isoformat(),
                "includePlanned": "true",
            },
        )
        self.assertEqual(forecast_response.status_code, status.HTTP_200_OK)
        self.assertIn("legendWithPlansValue", forecast_response.data)
        self.assertIn("points", forecast_response.data)
        self.assertEqual(
            Decimal(str(forecast_response.data["totalPlannedExpensesRub"])),
            Decimal("3000.00"),
        )

    def test_planned_transactions_validation_errors(self):
        self.authenticate()
        list_url = reverse("finance:planned-transaction-list")

        response = self.client.get(list_url, {"statusTab": "wrong"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            list_url,
            {
                "dateFrom": self.today.isoformat(),
                "dateTo": (self.today - timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"accounts": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"statuses": "pending,wrong"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            list_url,
            {
                "amountMin": "1000.00",
                "amountMax": "100.00",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"onlyDuplicates": "maybe"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(list_url, {"search": "x" * 101})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            reverse("finance:planned-transaction-calendar"),
            {
                "year": self.today.year,
                "month": 13,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get(
            reverse("finance:planned-transaction-forecast"),
            {
                "timeRange": "100 лет",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_planned_transaction_rejects_foreign_or_invalid_relations(self):
        self.authenticate()
        planned_date = self.today + timedelta(days=1)

        response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Чужой счёт",
                "kind": TransactionType.EXPENSE,
                "amountRub": "100.00",
                "categoryId": self.expense_category.id,
                "accountId": self.other_account.id,
                "plannedDate": planned_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Чужая категория",
                "kind": TransactionType.EXPENSE,
                "amountRub": "100.00",
                "categoryId": self.other_category.id,
                "accountId": self.account.id,
                "plannedDate": planned_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Неверный тип категории",
                "kind": TransactionType.INCOME,
                "amountRub": "100.00",
                "categoryId": self.expense_category.id,
                "accountId": self.account.id,
                "plannedDate": planned_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_planned_transaction_rejects_archived_or_inactive_relations(self):
        self.authenticate()
        planned_date = self.today + timedelta(days=1)

        self.account.is_archived = True
        self.account.is_active = False
        self.account.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Архивный счёт",
                "kind": TransactionType.EXPENSE,
                "amountRub": "100.00",
                "categoryId": self.expense_category.id,
                "accountId": self.account.id,
                "plannedDate": planned_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.account.is_archived = False
        self.account.is_active = True
        self.account.save(update_fields=["is_archived", "is_active", "updated_at"])
        self.expense_category.is_archived = True
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_archived", "is_active", "updated_at"])

        response = self.client.post(
            reverse("finance:planned-transaction-list"),
            data={
                "name": "Архивная категория",
                "kind": TransactionType.EXPENSE,
                "amountRub": "100.00",
                "categoryId": self.expense_category.id,
                "accountId": self.account.id,
                "plannedDate": planned_date.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
