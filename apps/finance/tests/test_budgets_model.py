from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models import (
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    TransactionType,
)
from apps.finance.tests.base import FinanceAPITestCase


class BudgetModelTests(FinanceAPITestCase):
    def _build_budget(self, **kwargs) -> Budget:
        data = {
            "user": self.user,
            "category": self.expense_category,
            "category_group": BudgetCategoryGroup.MAIN,
            "period_type": BudgetPeriodType.MONTH,
            "amount_limit": Decimal("10000.00"),
            "period_start": self.today.replace(day=1),
            "period_end": self.today.replace(day=28),
            "currency": "RUB",
            "kind": BudgetKind.EXPENSE,
            "rollover": False,
            "paused": False,
            "is_active": True,
            "comment": "",
        }
        data.update(kwargs)
        return Budget(**data)

    def test_budget_can_be_created_with_required_frontend_fields(self):
        budget = self._build_budget(
            category_group=BudgetCategoryGroup.FAMILY,
            period_type=BudgetPeriodType.QUARTER,
            amount_limit=Decimal("90000.00"),
            kind=BudgetKind.EXPENSE,
            rollover=True,
            comment="Семейный бюджет на квартал",
        )

        budget.full_clean()
        budget.save()
        budget.refresh_from_db()

        self.assertEqual(budget.category_group, BudgetCategoryGroup.FAMILY)
        self.assertEqual(budget.period_type, BudgetPeriodType.QUARTER)
        self.assertEqual(budget.kind, BudgetKind.EXPENSE)
        self.assertEqual(budget.currency, "RUB")
        self.assertTrue(budget.rollover)
        self.assertFalse(budget.paused)
        self.assertEqual(budget.status, "active")
        self.assertEqual(budget.limit_amount, Decimal("90000.00"))

    def test_budget_can_use_income_category_when_kind_is_income(self):
        budget = self._build_budget(
            category=self.income_category,
            kind=BudgetKind.INCOME,
            amount_limit=Decimal("150000.00"),
        )

        budget.full_clean()
        budget.save()
        budget.refresh_from_db()

        self.assertEqual(budget.category.type, TransactionType.INCOME)
        self.assertEqual(budget.kind, BudgetKind.INCOME)

    def test_budget_category_type_must_match_budget_kind(self):
        budget = self._build_budget(
            category=self.income_category,
            kind=BudgetKind.EXPENSE,
        )

        with self.assertRaises(ValidationError) as context:
            budget.full_clean()

        self.assertIn("category", context.exception.message_dict)

    def test_budget_category_must_belong_to_same_user(self):
        budget = self._build_budget(category=self.other_category)

        with self.assertRaises(ValidationError) as context:
            budget.full_clean()

        self.assertIn("category", context.exception.message_dict)

    def test_budget_rejects_inactive_or_archived_category(self):
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_active"])

        inactive_budget = self._build_budget(category=self.expense_category)

        with self.assertRaises(ValidationError) as inactive_context:
            inactive_budget.full_clean()

        self.assertIn("category", inactive_context.exception.message_dict)

        self.expense_category.is_archived = True
        self.expense_category.save(update_fields=["is_archived"])

        archived_budget = self._build_budget(category=self.expense_category)

        with self.assertRaises(ValidationError) as archived_context:
            archived_budget.full_clean()

        self.assertIn("category", archived_context.exception.message_dict)

    def test_budget_amount_limit_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("0.00"),
                    period_start=self.today,
                    period_end=self.today,
                )

    def test_budget_period_end_must_not_be_before_period_start(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("10000.00"),
                    period_start=self.today,
                    period_end=self.today - timezone.timedelta(days=1),
                )

    def test_budget_choice_fields_are_checked_on_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("10000.00"),
                    period_start=self.today,
                    period_end=self.today,
                    period_type="wrong",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("10000.00"),
                    period_start=self.today + timezone.timedelta(days=1),
                    period_end=self.today + timezone.timedelta(days=1),
                    kind="wrong",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("10000.00"),
                    period_start=self.today + timezone.timedelta(days=2),
                    period_end=self.today + timezone.timedelta(days=2),
                    category_group="wrong",
                )

    def test_budget_currency_is_normalized_before_save(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=self.today,
            period_end=self.today,
            currency="rub",
        )

        budget.refresh_from_db()

        self.assertEqual(budget.currency, "RUB")

    def test_budget_duplicate_category_kind_and_period_is_rejected(self):
        period_start = self.today
        period_end = self.today + timezone.timedelta(days=30)

        Budget.objects.create(
            user=self.user,
            category=self.expense_category,
            amount_limit=Decimal("10000.00"),
            period_start=period_start,
            period_end=period_end,
            period_type=BudgetPeriodType.MONTH,
            kind=BudgetKind.EXPENSE,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Budget.objects.create(
                    user=self.user,
                    category=self.expense_category,
                    amount_limit=Decimal("12000.00"),
                    period_start=period_start,
                    period_end=period_end,
                    period_type=BudgetPeriodType.MONTH,
                    kind=BudgetKind.EXPENSE,
                )

    def test_budget_paused_status_is_separate_from_active_flag(self):
        budget = self._build_budget(paused=True, is_active=True)

        budget.full_clean()
        budget.save()
        budget.refresh_from_db()

        self.assertTrue(budget.is_active)
        self.assertTrue(budget.paused)
        self.assertEqual(budget.status, "paused")
