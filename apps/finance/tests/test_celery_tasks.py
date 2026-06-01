from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import override_settings

from apps.finance.models import (
    PlannedStatus,
    PlannedTransaction,
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    Transaction,
    TransactionType,
)
from apps.finance.tasks import (
    convert_due_planned_transactions_task,
    refresh_currency_rates_task,
    run_due_recurring_transactions_task,
)
from apps.finance.testing import FinanceAPITestCase


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    CURRENCY_RATES_ENABLED=False,
)
class FinanceCeleryTaskTests(FinanceAPITestCase):
    def test_planned_transactions_task_converts_due_items(self):
        planned = PlannedTransaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            name="Плановый интернет",
            type=TransactionType.EXPENSE,
            amount=Decimal("890.00"),
            planned_date=date(2026, 6, 11),
            status=PlannedStatus.PENDING,
            comment="Домашний интернет",
        )

        result = convert_due_planned_transactions_task.apply(
            kwargs={"run_date": "2026-06-11"},
        ).get()

        planned.refresh_from_db()
        self.account.refresh_from_db()

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["converted_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(planned.status, PlannedStatus.CONVERTED)
        self.assertIsNotNone(planned.converted_transaction)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(self.account.balance, Decimal("9110.00"))

    def test_recurring_transactions_task_creates_due_operation(self):
        recurring = RecurringTransaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            name="Регулярный интернет",
            type=TransactionType.EXPENSE,
            amount=Decimal("890.00"),
            frequency=RecurringFrequency.DAILY,
            start_date=date(2026, 5, 20),
            next_charge_date=date(2026, 5, 20),
            status=RecurringStatus.ACTIVE,
            comment="Домашний интернет",
        )

        result = run_due_recurring_transactions_task.apply(
            kwargs={"run_date": "2026-05-20"},
        ).get()

        recurring.refresh_from_db()
        self.account.refresh_from_db()

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(recurring.created_count, 1)
        self.assertEqual(recurring.last_charge_date, date(2026, 5, 20))
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(self.account.balance, Decimal("9110.00"))

    def test_currency_rates_task_is_safe_without_currency_settings(self):
        result = refresh_currency_rates_task.apply().get()

        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["refreshed_count"], 0)
        self.assertEqual(result["failed_count"], 0)
