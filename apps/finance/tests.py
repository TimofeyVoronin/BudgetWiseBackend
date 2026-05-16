from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.finance.models import (
    Account,
    Budget,
    Category,
    Goal,
    Transaction,
    TransactionType,
)


User = get_user_model()


class FinanceIntegrityConstraintsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="timofey",
            email="timofey@example.com",
            password="test-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="test-password-123",
        )

        self.account = Account.objects.create(
            user=self.user,
            name="Основная карта",
            balance=Decimal("10000.00"),
            currency="RUB",
        )
        self.other_account = Account.objects.create(
            user=self.other_user,
            name="Основная карта",
            balance=Decimal("5000.00"),
            currency="RUB",
        )

        self.expense_category = Category.objects.create(
            user=self.user,
            name="Продукты",
            type=TransactionType.EXPENSE,
        )
        self.income_category = Category.objects.create(
            user=self.user,
            name="Зарплата",
            type=TransactionType.INCOME,
        )
        self.other_category = Category.objects.create(
            user=self.other_user,
            name="Продукты",
            type=TransactionType.EXPENSE,
        )

    def test_account_name_is_unique_per_user(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Account.objects.create(
                    user=self.user,
                    name="Основная карта",
                    balance=Decimal("0.00"),
                    currency="RUB",
                )

    def test_same_account_name_is_allowed_for_different_users(self):
        account = Account.objects.create(
            user=self.user,
            name="Наличные",
            balance=Decimal("1000.00"),
            currency="RUB",
        )

        other_account = Account.objects.create(
            user=self.other_user,
            name="Наличные",
            balance=Decimal("2000.00"),
            currency="RUB",
        )

        self.assertNotEqual(account.id, other_account.id)

    def test_category_name_and_type_are_unique_per_user(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(
                    user=self.user,
                    name="Продукты",
                    type=TransactionType.EXPENSE,
                )

    def test_same_category_name_is_allowed_for_different_types(self):
        category = Category.objects.create(
            user=self.user,
            name="Подарки",
            type=TransactionType.EXPENSE,
        )

        another_category = Category.objects.create(
            user=self.user,
            name="Подарки",
            type=TransactionType.INCOME,
        )

        self.assertNotEqual(category.id, another_category.id)

    def test_transaction_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    user=self.user,
                    account=self.account,
                    category=self.expense_category,
                    type=TransactionType.EXPENSE,
                    amount=Decimal("0.00"),
                    operation_date=timezone.localdate(),
                )

    def test_transaction_account_must_belong_to_same_user(self):
        operation = Transaction(
            user=self.user,
            account=self.other_account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            operation_date=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            operation.full_clean()

    def test_transaction_category_must_belong_to_same_user(self):
        operation = Transaction(
            user=self.user,
            account=self.account,
            category=self.other_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            operation_date=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            operation.full_clean()

    def test_transaction_type_must_match_category_type(self):
        operation = Transaction(
            user=self.user,
            account=self.account,
            category=self.income_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            operation_date=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            operation.full_clean()

    def test_account_with_transactions_is_protected_from_delete(self):
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            operation_date=timezone.localdate(),
        )

        with self.assertRaises(ProtectedError):
            self.account.delete()

    def test_category_with_transactions_is_protected_from_delete(self):
        Transaction.objects.create(
            user=self.user,
            account=self.account,
            category=self.expense_category,
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            operation_date=timezone.localdate(),
        )

        with self.assertRaises(ProtectedError):
            self.expense_category.delete()

    def test_budget_amount_limit_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("0.00"),
                    period_start=timezone.localdate(),
                    period_end=timezone.localdate(),
                )

    def test_budget_period_must_be_valid(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("10000.00"),
                    period_start=timezone.localdate(),
                    period_end=timezone.localdate() - timezone.timedelta(days=1),
                )

    def test_budget_category_must_be_expense_type(self):
        budget = Budget(
            user=self.user,
            category=self.income_category,
            amount_limit=Decimal("10000.00"),
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_budget_category_must_belong_to_same_user(self):
        budget = Budget(
            user=self.user,
            category=self.other_category,
            amount_limit=Decimal("10000.00"),
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_budget_category_must_be_active(self):
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_active"])

        budget = Budget(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_budget_category_must_not_be_archived(self):
        self.expense_category.is_archived = True
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_archived", "is_active"])

        budget = Budget(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            budget.full_clean()

    def test_category_rename_keeps_budget_relation(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )

        self.expense_category.name = "Продукты и супермаркеты"
        self.expense_category.save(update_fields=["name"])

        budget.refresh_from_db()
        self.expense_category.refresh_from_db()

        self.assertEqual(budget.category_id, self.expense_category.id)
        self.assertEqual(self.expense_category.name, "Продукты и супермаркеты")

    def test_goal_target_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Goal.objects.create(
                    user=self.user,
                    name="Отпуск",
                    target_amount=Decimal("0.00"),
                    current_amount=Decimal("0.00"),
                )

    def test_goal_current_amount_must_not_be_negative(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Goal.objects.create(
                    user=self.user,
                    name="Резерв",
                    target_amount=Decimal("100000.00"),
                    current_amount=Decimal("-1.00"),
                )

    def test_goal_name_is_unique_per_user(self):
        Goal.objects.create(
            user=self.user,
            name="Отпуск",
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("0.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Goal.objects.create(
                    user=self.user,
                    name="Отпуск",
                    target_amount=Decimal("150000.00"),
                    current_amount=Decimal("0.00"),
                )

    def test_goal_account_must_belong_to_same_user(self):
        goal = Goal(
            user=self.user,
            account=self.other_account,
            name="Резерв",
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("0.00"),
        )

        with self.assertRaises(ValidationError):
            goal.full_clean()