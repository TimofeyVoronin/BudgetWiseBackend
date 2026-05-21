from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.finance.models import (
    Tag,
    TransactionTemplate,
    TransactionTemplateIconTone,
    TransactionTemplateStatus,
    TransactionType,
)
from apps.finance.tests.base import FinanceAPITestCase


class TransactionTemplateModelTests(FinanceAPITestCase):
    def _build_template(self, **kwargs) -> TransactionTemplate:
        data = {
            "user": self.user,
            "name": "Обед в офисе",
            "kind": TransactionType.EXPENSE,
            "amount": Decimal("450.00"),
            "currency": "RUB",
            "account": self.account,
            "category": self.expense_category,
            "note": "Быстрый шаблон для обеда",
            "status": TransactionTemplateStatus.ACTIVE,
            "is_default": False,
        }
        data.update(kwargs)
        return TransactionTemplate(**data)

    def test_transaction_template_can_be_created_with_required_fields(self):
        tag = Tag.objects.create(
            user=self.user,
            name="обед",
            color="#66BB6A",
            icon="cart",
        )

        template = self._build_template()
        template.full_clean()
        template.save()
        template.tags.add(tag)
        template.refresh_from_db()

        self.assertEqual(template.name, "Обед в офисе")
        self.assertEqual(template.normalized_name, "обед в офисе")
        self.assertEqual(template.kind, TransactionType.EXPENSE)
        self.assertEqual(template.amount, Decimal("450.00"))
        self.assertEqual(template.currency, "RUB")
        self.assertEqual(template.status, TransactionTemplateStatus.ACTIVE)
        self.assertFalse(template.is_default)
        self.assertFalse(template.is_archived)
        self.assertEqual(template.use_count, 0)
        self.assertIsNone(template.last_used_at)
        self.assertEqual(list(template.tags.values_list("id", flat=True)), [tag.id])

    def test_income_template_can_use_income_category(self):
        template = self._build_template(
            name="Зарплата",
            kind=TransactionType.INCOME,
            amount=Decimal("85000.00"),
            category=self.income_category,
        )

        template.full_clean()
        template.save()
        template.refresh_from_db()

        self.assertEqual(template.kind, TransactionType.INCOME)
        self.assertEqual(template.category.type, TransactionType.INCOME)
        self.assertEqual(template.icon_tone, TransactionTemplateIconTone.SUCCESS)

    def test_template_category_type_must_match_kind(self):
        template = self._build_template(
            kind=TransactionType.EXPENSE,
            category=self.income_category,
        )

        with self.assertRaises(ValidationError) as context:
            template.full_clean()

        self.assertIn("category", context.exception.message_dict)

    def test_template_account_and_category_must_belong_to_user(self):
        template_with_foreign_account = self._build_template(account=self.other_account)

        with self.assertRaises(ValidationError) as account_context:
            template_with_foreign_account.full_clean()

        self.assertIn("account", account_context.exception.message_dict)

        template_with_foreign_category = self._build_template(category=self.other_category)

        with self.assertRaises(ValidationError) as category_context:
            template_with_foreign_category.full_clean()

        self.assertIn("category", category_context.exception.message_dict)

    def test_template_rejects_inactive_or_archived_account(self):
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        inactive_account_template = self._build_template(account=self.account)

        with self.assertRaises(ValidationError) as inactive_context:
            inactive_account_template.full_clean()

        self.assertIn("account", inactive_context.exception.message_dict)

        self.account.is_active = True
        self.account.is_archived = True
        self.account.save(update_fields=["is_active", "is_archived"])

        archived_account_template = self._build_template(account=self.account)

        with self.assertRaises(ValidationError) as archived_context:
            archived_account_template.full_clean()

        self.assertIn("account", archived_context.exception.message_dict)

    def test_template_rejects_inactive_or_archived_category(self):
        self.expense_category.is_active = False
        self.expense_category.save(update_fields=["is_active"])

        inactive_category_template = self._build_template(category=self.expense_category)

        with self.assertRaises(ValidationError) as inactive_context:
            inactive_category_template.full_clean()

        self.assertIn("category", inactive_context.exception.message_dict)

        self.expense_category.is_active = True
        self.expense_category.is_archived = True
        self.expense_category.save(update_fields=["is_active", "is_archived"])

        archived_category_template = self._build_template(category=self.expense_category)

        with self.assertRaises(ValidationError) as archived_context:
            archived_category_template.full_clean()

        self.assertIn("category", archived_context.exception.message_dict)

    def test_template_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionTemplate.objects.create(
                    user=self.user,
                    name="Нулевая сумма",
                    kind=TransactionType.EXPENSE,
                    amount=Decimal("0.00"),
                    account=self.account,
                    category=self.expense_category,
                )

    def test_template_choice_fields_are_checked_on_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionTemplate.objects.create(
                    user=self.user,
                    name="Некорректный тип",
                    kind="wrong",
                    amount=Decimal("100.00"),
                    account=self.account,
                    category=self.expense_category,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionTemplate.objects.create(
                    user=self.user,
                    name="Некорректный статус",
                    kind=TransactionType.EXPENSE,
                    amount=Decimal("100.00"),
                    account=self.account,
                    category=self.expense_category,
                    status="wrong",
                )

    def test_template_currency_is_normalized_before_save(self):
        template = TransactionTemplate.objects.create(
            user=self.user,
            name="Кофе",
            kind=TransactionType.EXPENSE,
            amount=Decimal("180.00"),
            currency="rub",
            account=self.account,
            category=self.expense_category,
        )

        template.refresh_from_db()

        self.assertEqual(template.currency, "RUB")

    def test_active_template_duplicate_name_is_rejected_per_user(self):
        TransactionTemplate.objects.create(
            user=self.user,
            name="Такси домой",
            kind=TransactionType.EXPENSE,
            amount=Decimal("320.00"),
            account=self.account,
            category=self.transport_category,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionTemplate.objects.create(
                    user=self.user,
                    name="  такси   домой  ",
                    kind=TransactionType.EXPENSE,
                    amount=Decimal("350.00"),
                    account=self.account,
                    category=self.transport_category,
                )

    def test_archived_template_allows_reusing_name_for_active_template(self):
        archived_template = TransactionTemplate.objects.create(
            user=self.user,
            name="Подписка Netflix",
            kind=TransactionType.EXPENSE,
            amount=Decimal("599.00"),
            account=self.account,
            category=self.expense_category,
            status=TransactionTemplateStatus.ARCHIVED,
            is_default=True,
        )
        archived_template.refresh_from_db()

        active_template = TransactionTemplate.objects.create(
            user=self.user,
            name="Подписка Netflix",
            kind=TransactionType.EXPENSE,
            amount=Decimal("699.00"),
            account=self.account,
            category=self.expense_category,
            status=TransactionTemplateStatus.ACTIVE,
        )

        self.assertFalse(archived_template.is_default)
        self.assertEqual(active_template.status, TransactionTemplateStatus.ACTIVE)

    def test_only_one_active_default_template_per_user_and_kind(self):
        TransactionTemplate.objects.create(
            user=self.user,
            name="Основной расход",
            kind=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            account=self.account,
            category=self.expense_category,
            is_default=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TransactionTemplate.objects.create(
                    user=self.user,
                    name="Другой расход",
                    kind=TransactionType.EXPENSE,
                    amount=Decimal("200.00"),
                    account=self.account,
                    category=self.transport_category,
                    is_default=True,
                )

        income_default = TransactionTemplate.objects.create(
            user=self.user,
            name="Основной доход",
            kind=TransactionType.INCOME,
            amount=Decimal("85000.00"),
            account=self.account,
            category=self.income_category,
            is_default=True,
        )

        self.assertTrue(income_default.is_default)

    def test_archived_template_drops_default_flag_on_save(self):
        template = self._build_template(
            status=TransactionTemplateStatus.ARCHIVED,
            is_default=True,
        )

        template.full_clean()
        template.save()
        template.refresh_from_db()

        self.assertFalse(template.is_default)
        self.assertTrue(template.is_archived)

    def test_template_icon_uses_category_icon_and_tone_uses_kind(self):
        self.expense_category.icon = "coffee"
        self.expense_category.save(update_fields=["icon"])

        expense_template = self._build_template(category=self.expense_category)
        expense_template.full_clean()
        expense_template.save()

        self.assertEqual(expense_template.icon, "coffee")
        self.assertEqual(expense_template.icon_tone, TransactionTemplateIconTone.WARNING)
