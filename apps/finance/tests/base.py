from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.finance.models import Account, Category, Transaction, TransactionType


User = get_user_model()


class FinanceAPITestCase(TestCase):

    def setUp(self):
            self.client = APIClient()
            cache.clear()

            self.user = User.objects.create_user(
                username="demo",
                email="demo@example.com",
                password="demo-password-123",
            )
            self.other_user = User.objects.create_user(
                username="other",
                email="other@example.com",
                password="other-password-123",
            )

            self.account = Account.objects.create(
                user=self.user,
                name="Основная карта",
                balance=Decimal("10000.00"),
                currency="RUB",
            )
            self.cash_account = Account.objects.create(
                user=self.user,
                name="Наличные",
                balance=Decimal("3000.00"),
                currency="RUB",
            )
            self.other_account = Account.objects.create(
                user=self.other_user,
                name="Чужая карта",
                balance=Decimal("5000.00"),
                currency="RUB",
            )

            self.expense_category = Category.objects.create(
                user=self.user,
                name="Продукты",
                type=TransactionType.EXPENSE,
            )
            self.transport_category = Category.objects.create(
                user=self.user,
                name="Транспорт",
                type=TransactionType.EXPENSE,
            )
            self.income_category = Category.objects.create(
                user=self.user,
                name="Зарплата",
                type=TransactionType.INCOME,
            )
            self.other_category = Category.objects.create(
                user=self.other_user,
                name="Чужая категория",
                type=TransactionType.EXPENSE,
            )

            self.today = timezone.localdate()

    def authenticate(self):
            self.client.force_authenticate(user=self.user)

    def create_transaction(
            self,
            *,
            user=None,
            account=None,
            category=None,
            type=TransactionType.EXPENSE,
            amount="100.00",
            description="Тестовая операция",
            operation_date=None,
        ):
            return Transaction.objects.create(
                user=user or self.user,
                account=account or self.account,
                category=category or self.expense_category,
                type=type,
                amount=Decimal(amount),
                description=description,
                operation_date=operation_date or self.today,
            )

    def get_transaction_ids(self, response):
            return [item["id"] for item in response.data["results"]]
