from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
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


class Command(BaseCommand):
    help = "Create demo user and seed finance data for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="demo",
            help="Demo user username.",
        )
        parser.add_argument(
            "--email",
            default="demo@example.com",
            help="Demo user email.",
        )
        parser.add_argument(
            "--password",
            default="demo-password-123",
            help="Demo user password.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        email = options["email"]
        password = options["password"]

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
            },
        )

        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(self.style.SUCCESS(f"Created user: {username}"))
        else:
            self.stdout.write(self.style.WARNING(f"User already exists: {username}"))

        accounts = self._create_accounts(user)
        categories = self._create_categories(user)
        self._create_transactions(user, accounts, categories)
        self._create_budget(user, categories)
        self._create_goal(user, accounts)

        self.stdout.write(self.style.SUCCESS("Demo finance data has been prepared."))

    def _create_accounts(self, user):
        account_data = [
            {
                "name": "Основная карта",
                "balance": Decimal("75000.00"),
                "currency": "RUB",
            },
            {
                "name": "Наличные",
                "balance": Decimal("12000.00"),
                "currency": "RUB",
            },
            {
                "name": "Накопительный счёт",
                "balance": Decimal("150000.00"),
                "currency": "RUB",
            },
        ]

        accounts = {}

        for item in account_data:
            account, _ = Account.objects.get_or_create(
                user=user,
                name=item["name"],
                defaults={
                    "balance": item["balance"],
                    "currency": item["currency"],
                    "is_active": True,
                },
            )
            accounts[item["name"]] = account

        return accounts

    def _create_categories(self, user):
        category_data = [
            {
                "name": "Зарплата",
                "type": TransactionType.INCOME,
            },
            {
                "name": "Подработка",
                "type": TransactionType.INCOME,
            },
            {
                "name": "Продукты",
                "type": TransactionType.EXPENSE,
            },
            {
                "name": "Транспорт",
                "type": TransactionType.EXPENSE,
            },
            {
                "name": "Аренда",
                "type": TransactionType.EXPENSE,
            },
            {
                "name": "Здоровье",
                "type": TransactionType.EXPENSE,
            },
            {
                "name": "Развлечения",
                "type": TransactionType.EXPENSE,
            },
        ]

        categories = {}

        for item in category_data:
            category, _ = Category.objects.get_or_create(
                user=user,
                name=item["name"],
                type=item["type"],
                defaults={
                    "is_active": True,
                },
            )
            categories[item["name"]] = category

        return categories

    def _create_transactions(self, user, accounts, categories):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        transaction_data = [
            {
                "account": accounts["Основная карта"],
                "category": categories["Зарплата"],
                "type": TransactionType.INCOME,
                "amount": Decimal("90000.00"),
                "description": "Зарплата за месяц",
                "operation_date": month_start,
            },
            {
                "account": accounts["Основная карта"],
                "category": categories["Продукты"],
                "type": TransactionType.EXPENSE,
                "amount": Decimal("3200.00"),
                "description": "Покупка продуктов",
                "operation_date": today,
            },
            {
                "account": accounts["Основная карта"],
                "category": categories["Транспорт"],
                "type": TransactionType.EXPENSE,
                "amount": Decimal("1200.00"),
                "description": "Транспортные расходы",
                "operation_date": today,
            },
            {
                "account": accounts["Основная карта"],
                "category": categories["Аренда"],
                "type": TransactionType.EXPENSE,
                "amount": Decimal("30000.00"),
                "description": "Аренда квартиры",
                "operation_date": month_start,
            },
            {
                "account": accounts["Наличные"],
                "category": categories["Развлечения"],
                "type": TransactionType.EXPENSE,
                "amount": Decimal("2500.00"),
                "description": "Кино и кафе",
                "operation_date": today,
            },
        ]

        for item in transaction_data:
            Transaction.objects.get_or_create(
                user=user,
                account=item["account"],
                category=item["category"],
                type=item["type"],
                amount=item["amount"],
                description=item["description"],
                operation_date=item["operation_date"],
            )

    def _create_budget(self, user, categories):
        today = timezone.localdate()
        period_start = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        period_end = date(today.year, today.month, last_day)

        Budget.objects.get_or_create(
            user=user,
            category=categories["Продукты"],
            period_start=period_start,
            period_end=period_end,
            defaults={
                "amount_limit": Decimal("25000.00"),
                "is_active": True,
            },
        )

    def _create_goal(self, user, accounts):
        Goal.objects.get_or_create(
            user=user,
            name="Финансовая подушка",
            defaults={
                "account": accounts["Накопительный счёт"],
                "target_amount": Decimal("300000.00"),
                "current_amount": Decimal("150000.00"),
                "status": "active",
            },
        )