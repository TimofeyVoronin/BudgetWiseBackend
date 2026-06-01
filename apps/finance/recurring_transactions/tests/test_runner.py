from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command

from apps.finance.models import (
    Account,
    RecurringChargeStatus,
    RecurringFrequency,
    RecurringStatus,
    RecurringTransaction,
    RecurringTransactionCharge,
    Transaction,
    TransactionType,
)
from apps.finance.recurring_transactions.services import (
    RECURRING_ERROR_ACCOUNT_ARCHIVED,
    RECURRING_ERROR_CATEGORY_ARCHIVED,
    RECURRING_ERROR_INSUFFICIENT_FUNDS,
    run_due_recurring_transactions,
    run_single_recurring_transaction,
)
from apps.finance.testing import FinanceAPITestCase


class FinanceRecurringTransactionsRunnerTests(FinanceAPITestCase):
    def create_recurring(
        self,
        *,
        user=None,
        account=None,
        category=None,
        name="Автосписание",
        type=TransactionType.EXPENSE,
        amount="100.00",
        frequency=RecurringFrequency.DAILY,
        start_date=None,
        next_charge_date=None,
        status=RecurringStatus.ACTIVE,
        has_end=False,
        end_date=None,
        day_of_month=None,
        comment="",
    ):
        start_date = start_date or date(2026, 5, 20)
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
            comment=comment,
        )

    def test_runner_creates_transaction_charge_and_updates_balance(self):
        recurring = self.create_recurring(
            name="Интернет",
            amount="890.00",
            next_charge_date=date(2026, 5, 20),
            comment="Домашний интернет",
        )

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.processed_count, 1)
        self.assertEqual(summary.created_count, 1)
        self.assertEqual(summary.failed_count, 0)

        recurring.refresh_from_db()
        self.account.refresh_from_db()

        self.assertEqual(recurring.last_charge_date, date(2026, 5, 20))
        self.assertEqual(recurring.next_charge_date, date(2026, 5, 21))
        self.assertEqual(recurring.created_count, 1)
        self.assertEqual(recurring.status, RecurringStatus.ACTIVE)
        self.assertEqual(recurring.last_error_code, "")
        self.assertEqual(self.account.balance, Decimal("9110.00"))

        transaction = Transaction.objects.get()
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.account, self.account)
        self.assertEqual(transaction.category, self.expense_category)
        self.assertEqual(transaction.type, TransactionType.EXPENSE)
        self.assertEqual(transaction.amount, Decimal("890.00"))
        self.assertEqual(transaction.operation_date, date(2026, 5, 20))
        self.assertEqual(transaction.description, "Домашний интернет")

        charge = RecurringTransactionCharge.objects.get()
        self.assertEqual(charge.recurring_transaction, recurring)
        self.assertEqual(charge.transaction, transaction)
        self.assertEqual(charge.status, RecurringChargeStatus.SUCCESS)
        self.assertEqual(charge.scheduled_date, date(2026, 5, 20))

    def test_income_runner_increases_account_balance(self):
        recurring = self.create_recurring(
            name="Зарплата",
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="5000.00",
            next_charge_date=date(2026, 5, 20),
        )

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.created_count, 1)
        recurring.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("15000.00"))
        self.assertEqual(recurring.created_count, 1)

    def test_runner_does_not_create_duplicate_for_same_scheduled_date(self):
        recurring = self.create_recurring(next_charge_date=date(2026, 5, 20))

        first_summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))
        second_summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(first_summary.created_count, 1)
        self.assertEqual(second_summary.created_count, 0)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(RecurringTransactionCharge.objects.count(), 1)

        recurring.refresh_from_db()
        self.assertEqual(recurring.next_charge_date, date(2026, 5, 21))

    def test_runner_creates_failed_charge_when_funds_are_insufficient(self):
        recurring = self.create_recurring(
            amount="20000.00",
            next_charge_date=date(2026, 5, 20),
        )

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.created_count, 0)
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        recurring.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("10000.00"))
        self.assertEqual(recurring.status, RecurringStatus.ERROR)
        self.assertEqual(recurring.last_error_code, RECURRING_ERROR_INSUFFICIENT_FUNDS)
        self.assertEqual(recurring.next_charge_date, date(2026, 5, 21))

        charge = RecurringTransactionCharge.objects.get()
        self.assertEqual(charge.status, RecurringChargeStatus.FAILED)
        self.assertEqual(charge.error_code, RECURRING_ERROR_INSUFFICIENT_FUNDS)

    def test_runner_creates_failed_charge_for_archived_account(self):
        self.account.is_archived = True
        self.account.is_active = True
        self.account.save(update_fields=["is_archived", "is_active", "updated_at"])

        recurring = self.create_recurring(next_charge_date=date(2026, 5, 20))

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.ERROR)
        self.assertEqual(recurring.last_error_code, RECURRING_ERROR_ACCOUNT_ARCHIVED)

        charge = RecurringTransactionCharge.objects.get()
        self.assertEqual(charge.status, RecurringChargeStatus.FAILED)
        self.assertEqual(charge.error_code, RECURRING_ERROR_ACCOUNT_ARCHIVED)

    def test_runner_creates_failed_charge_for_archived_category(self):
        self.expense_category.is_archived = True
        self.expense_category.is_active = True
        self.expense_category.save(update_fields=["is_archived", "is_active", "updated_at"])

        recurring = self.create_recurring(next_charge_date=date(2026, 5, 20))

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.ERROR)
        self.assertEqual(recurring.last_error_code, RECURRING_ERROR_CATEGORY_ARCHIVED)

        charge = RecurringTransactionCharge.objects.get()
        self.assertEqual(charge.status, RecurringChargeStatus.FAILED)
        self.assertEqual(charge.error_code, RECURRING_ERROR_CATEGORY_ARCHIVED)

    def test_runner_ignores_paused_completed_and_future_recurring_transactions(self):
        self.create_recurring(
            name="На паузе",
            status=RecurringStatus.PAUSED,
            next_charge_date=date(2026, 5, 20),
        )
        self.create_recurring(
            name="Завершена",
            status=RecurringStatus.COMPLETED,
            next_charge_date=date(2026, 5, 20),
        )
        self.create_recurring(
            name="Будущая",
            status=RecurringStatus.ACTIVE,
            next_charge_date=date(2026, 5, 21),
        )

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.created_count, 0)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(RecurringTransactionCharge.objects.count(), 0)

    def test_runner_completes_recurring_after_end_date(self):
        recurring = self.create_recurring(
            frequency=RecurringFrequency.DAILY,
            start_date=date(2026, 5, 20),
            next_charge_date=date(2026, 5, 20),
            has_end=True,
            end_date=date(2026, 5, 20),
        )

        summary = run_due_recurring_transactions(run_date=date(2026, 5, 20))

        self.assertEqual(summary.created_count, 1)
        recurring.refresh_from_db()
        self.assertEqual(recurring.status, RecurringStatus.COMPLETED)
        self.assertEqual(recurring.created_count, 1)
        self.assertEqual(recurring.last_charge_date, date(2026, 5, 20))

    def test_runner_skips_existing_charge_for_same_scheduled_date(self):
        recurring = self.create_recurring(next_charge_date=date(2026, 5, 20))
        RecurringTransactionCharge.objects.create(
            user=self.user,
            recurring_transaction=recurring,
            scheduled_date=date(2026, 5, 20),
            amount=Decimal("100.00"),
            status=RecurringChargeStatus.SUCCESS,
        )

        summary = run_single_recurring_transaction(
            recurring_id=recurring.id,
            run_date=date(2026, 5, 20),
        )

        self.assertEqual(summary.created_count, 0)
        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        recurring.refresh_from_db()
        self.assertEqual(recurring.next_charge_date, date(2026, 5, 21))

    def test_dry_run_does_not_create_transactions_or_charges(self):
        recurring = self.create_recurring(next_charge_date=date(2026, 5, 20))

        summary = run_due_recurring_transactions(
            run_date=date(2026, 5, 20),
            dry_run=True,
        )

        self.assertEqual(summary.created_count, 0)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(RecurringTransactionCharge.objects.count(), 0)

        recurring.refresh_from_db()
        self.assertEqual(recurring.next_charge_date, date(2026, 5, 20))
        self.assertEqual(recurring.created_count, 0)

    def test_management_command_runs_runner(self):
        self.create_recurring(next_charge_date=date(2026, 5, 20))
        output = StringIO()

        call_command(
            "run_recurring_transactions",
            "--date",
            "2026-05-20",
            stdout=output,
        )

        self.assertIn("Recurring transactions processing finished", output.getvalue())
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(RecurringTransactionCharge.objects.count(), 1)

    def test_management_command_dry_run_does_not_create_data(self):
        self.create_recurring(next_charge_date=date(2026, 5, 20))
        output = StringIO()

        call_command(
            "run_recurring_transactions",
            "--date",
            "2026-05-20",
            "--dry-run",
            stdout=output,
        )

        command_output = output.getvalue().lower()

        self.assertIn("processed=1", command_output)
        self.assertIn("created=0", command_output)
        self.assertIn("skipped=1", command_output)
        self.assertIn("тестовый запуск", command_output)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(RecurringTransactionCharge.objects.count(), 0)

    def test_runner_respects_limit(self):
        first = self.create_recurring(name="Первый", next_charge_date=date(2026, 5, 20))
        second = self.create_recurring(name="Второй", next_charge_date=date(2026, 5, 20))

        summary = run_due_recurring_transactions(
            run_date=date(2026, 5, 20),
            limit=1,
        )

        self.assertEqual(summary.created_count, 1)
        self.assertEqual(Transaction.objects.count(), 1)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.next_charge_date, date(2026, 5, 20))
