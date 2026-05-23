from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.finance.models import (
    PlannedStatus,
    PlannedTransaction,
    Transaction,
    TransactionType,
)
from apps.finance.planned_transactions.services import (
    PLANNED_CONVERSION_CONVERTED,
    PLANNED_CONVERSION_SKIPPED,
    PLANNED_ERROR_ACCOUNT_ARCHIVED,
    PLANNED_ERROR_CATEGORY_ARCHIVED,
    PLANNED_ERROR_INSUFFICIENT_FUNDS,
    PLANNED_ERROR_NOT_CONVERTIBLE,
    PlannedConversionError,
    convert_planned_transaction,
    run_due_planned_transactions,
)
from apps.finance.testing import FinanceAPITestCase


class FinancePlannedTransactionsRunnerTests(FinanceAPITestCase):
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
    ):
        return PlannedTransaction.objects.create(
            user=user or self.user,
            account=account or self.account,
            category=category or self.expense_category,
            name=name,
            type=type,
            amount=Decimal(amount),
            planned_date=planned_date or date(2026, 6, 11),
            status=status,
            include_in_forecast=include_in_forecast,
            comment=comment,
        )

    def test_runner_converts_due_planned_transaction_and_updates_balance(self):
        planned = self.create_planned(
            name="Интернет",
            amount="890.00",
            planned_date=date(2026, 6, 11),
            comment="Домашний интернет",
        )

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.processed_count, 1)
        self.assertEqual(summary.converted_count, 1)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(summary.skipped_count, 0)

        planned.refresh_from_db()
        self.account.refresh_from_db()
        transaction = Transaction.objects.get()

        self.assertEqual(planned.status, PlannedStatus.CONVERTED)
        self.assertEqual(planned.converted_transaction, transaction)
        self.assertIsNotNone(planned.converted_at)
        self.assertEqual(planned.last_error_code, "")
        self.assertEqual(planned.last_error_message, "")
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.account, self.account)
        self.assertEqual(transaction.category, self.expense_category)
        self.assertEqual(transaction.type, TransactionType.EXPENSE)
        self.assertEqual(transaction.amount, Decimal("890.00"))
        self.assertEqual(transaction.operation_date, date(2026, 6, 11))
        self.assertEqual(transaction.description, "Домашний интернет")
        self.assertEqual(self.account.balance, Decimal("9110.00"))

        self.assertEqual(summary.items[0].planned_id, planned.id)
        self.assertEqual(summary.items[0].status, PLANNED_CONVERSION_CONVERTED)
        self.assertEqual(summary.items[0].transaction_id, transaction.id)

    def test_income_conversion_increases_account_balance(self):
        planned = self.create_planned(
            name="Премия",
            type=TransactionType.INCOME,
            category=self.income_category,
            amount="5000.00",
            planned_date=date(2026, 6, 11),
        )

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.converted_count, 1)
        planned.refresh_from_db()
        self.account.refresh_from_db()
        transaction = Transaction.objects.get()
        self.assertEqual(planned.converted_transaction, transaction)
        self.assertEqual(transaction.type, TransactionType.INCOME)
        self.assertEqual(self.account.balance, Decimal("15000.00"))

    def test_runner_ignores_future_cancelled_converted_and_overdue_items(self):
        self.create_planned(
            name="Будущая",
            planned_date=date(2026, 6, 12),
            status=PlannedStatus.PENDING,
        )
        self.create_planned(
            name="Отмененная",
            planned_date=date(2026, 6, 11),
            status=PlannedStatus.CANCELLED,
        )
        self.create_planned(
            name="Просроченная",
            planned_date=date(2026, 6, 11),
            status=PlannedStatus.OVERDUE,
        )
        converted = self.create_planned(
            name="Уже конвертирована",
            planned_date=date(2026, 6, 11),
            status=PlannedStatus.CONVERTED,
        )
        transaction = Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            description="Создана раньше",
            operation_date=date(2026, 6, 10),
        )
        converted.converted_transaction = transaction
        converted.save(update_fields=["converted_transaction", "updated_at"])

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.processed_count, 0)
        self.assertEqual(summary.converted_count, 0)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(summary.skipped_count, 0)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_direct_conversion_is_idempotent_for_already_converted_item(self):
        planned = self.create_planned(planned_date=date(2026, 6, 11))
        first_result = convert_planned_transaction(
            planned_id=planned.id,
            user=self.user,
            operation_date=date(2026, 6, 11),
        )
        second_result = convert_planned_transaction(
            planned_id=planned.id,
            user=self.user,
            operation_date=date(2026, 6, 11),
        )

        self.assertEqual(first_result.status, PLANNED_CONVERSION_CONVERTED)
        self.assertEqual(second_result.status, PLANNED_CONVERSION_SKIPPED)
        self.assertEqual(first_result.transaction_id, second_result.transaction_id)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_direct_conversion_rejects_foreign_user_scope(self):
        planned = self.create_planned(planned_date=date(2026, 6, 11))

        with self.assertRaises(PlannedConversionError) as context:
            convert_planned_transaction(
                planned_id=planned.id,
                user=self.other_user,
                operation_date=date(2026, 6, 11),
            )

        self.assertEqual(context.exception.code, PLANNED_ERROR_NOT_CONVERTIBLE)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_runner_marks_overdue_when_funds_are_insufficient(self):
        planned = self.create_planned(
            amount="20000.00",
            planned_date=date(2026, 6, 11),
        )

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.processed_count, 1)
        self.assertEqual(summary.converted_count, 0)
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        planned.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.OVERDUE)
        self.assertEqual(planned.last_error_code, PLANNED_ERROR_INSUFFICIENT_FUNDS)
        self.assertIn("Недостаточно средств", planned.last_error_message)
        self.assertIsNotNone(planned.last_failed_at)
        self.assertEqual(self.account.balance, Decimal("10000.00"))
        self.assertEqual(summary.items[0].error_code, PLANNED_ERROR_INSUFFICIENT_FUNDS)

    def test_runner_marks_overdue_for_archived_account(self):
        self.account.is_archived = True
        self.account.is_active = True
        self.account.save(update_fields=["is_archived", "is_active", "updated_at"])
        planned = self.create_planned(planned_date=date(2026, 6, 11))

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)
        planned.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.OVERDUE)
        self.assertEqual(planned.last_error_code, PLANNED_ERROR_ACCOUNT_ARCHIVED)

    def test_runner_marks_overdue_for_archived_category(self):
        self.expense_category.is_archived = True
        self.expense_category.is_active = True
        self.expense_category.save(update_fields=["is_archived", "is_active", "updated_at"])
        planned = self.create_planned(planned_date=date(2026, 6, 11))

        summary = run_due_planned_transactions(run_date=date(2026, 6, 11))

        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)
        planned.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.OVERDUE)
        self.assertEqual(planned.last_error_code, PLANNED_ERROR_CATEGORY_ARCHIVED)

    def test_runner_respects_limit(self):
        first = self.create_planned(
            name="Первый",
            amount="100.00",
            planned_date=date(2026, 6, 11),
        )
        second = self.create_planned(
            name="Второй",
            amount="200.00",
            planned_date=date(2026, 6, 11),
        )

        summary = run_due_planned_transactions(
            run_date=date(2026, 6, 11),
            limit=1,
        )

        self.assertEqual(summary.processed_count, 1)
        self.assertEqual(summary.converted_count, 1)
        self.assertEqual(Transaction.objects.count(), 1)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, PlannedStatus.CONVERTED)
        self.assertEqual(second.status, PlannedStatus.PENDING)

    def test_dry_run_does_not_create_transaction_or_update_planned_item(self):
        planned = self.create_planned(planned_date=date(2026, 6, 11))

        summary = run_due_planned_transactions(
            run_date=date(2026, 6, 11),
            dry_run=True,
        )

        self.assertEqual(summary.processed_count, 1)
        self.assertEqual(summary.converted_count, 0)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(Transaction.objects.count(), 0)

        planned.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(planned.status, PlannedStatus.PENDING)
        self.assertIsNone(planned.converted_transaction)
        self.assertEqual(self.account.balance, Decimal("10000.00"))
        self.assertIn("Тестовый запуск", summary.items[0].message)

    def test_management_command_converts_planned_transactions(self):
        self.create_planned(planned_date=date(2026, 6, 11))
        output = StringIO()

        call_command(
            "convert_planned_transactions",
            "--date",
            "2026-06-11",
            stdout=output,
        )

        command_output = output.getvalue()
        self.assertIn("Planned transactions conversion finished", command_output)
        self.assertIn("processed=1", command_output)
        self.assertIn("converted=1", command_output)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(PlannedTransaction.objects.get().status, PlannedStatus.CONVERTED)

    def test_management_command_dry_run_does_not_create_data(self):
        self.create_planned(planned_date=date(2026, 6, 11))
        output = StringIO()

        call_command(
            "convert_planned_transactions",
            "--date",
            "2026-06-11",
            "--dry-run",
            stdout=output,
        )

        command_output = output.getvalue().lower()
        self.assertIn("processed=1", command_output)
        self.assertIn("converted=0", command_output)
        self.assertIn("skipped=1", command_output)
        self.assertIn("тестовый запуск", command_output)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(PlannedTransaction.objects.get().status, PlannedStatus.PENDING)

    def test_management_command_rejects_invalid_arguments(self):
        with self.assertRaises(CommandError):
            call_command(
                "convert_planned_transactions",
                "--date",
                "wrong-date",
                stdout=StringIO(),
            )

        with self.assertRaises(CommandError):
            call_command(
                "convert_planned_transactions",
                "--date",
                "2026-06-11",
                "--limit",
                "0",
                stdout=StringIO(),
            )

    def test_summary_as_dict_contains_serializable_items(self):
        planned = self.create_planned(planned_date=date(2026, 6, 11))

        summary = run_due_planned_transactions(
            run_date=date(2026, 6, 11),
            dry_run=True,
        )
        data = summary.as_dict()

        self.assertEqual(data["processed_count"], 1)
        self.assertEqual(data["skipped_count"], 1)
        self.assertEqual(data["items"][0]["planned_id"], planned.id)
        self.assertEqual(data["items"][0]["planned_date"], "2026-06-11")
