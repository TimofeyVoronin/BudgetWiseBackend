# Generated for BUD-1071 currency management.

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_CURRENCIES = [
    ("RUB", "Российский рубль", "₽", "rub", 2, True),
    ("USD", "Доллар США", "$", "usd", 2, True),
    ("EUR", "Евро", "€", "eur", 2, True),
    ("KZT", "Казахстанский тенге", "₸", "kzt", 2, True),
    ("CNY", "Китайский юань", "¥", "cny", 2, True),
    ("THB", "Тайский бат", "฿", "thb", 2, False),
    ("BYN", "Белорусский рубль", "Br", "byn", 2, False),
    ("GBP", "Фунт стерлингов", "£", "gbp", 2, True),
    ("BTC", "Bitcoin", "₿", "btc", 8, False),
    ("ETH", "Ethereum", "Ξ", "eth", 8, False),
]


def seed_default_currencies(apps, schema_editor):
    Currency = apps.get_model("finance", "Currency")

    for code, name, symbol, flag_icon, decimal_places, is_popular in DEFAULT_CURRENCIES:
        Currency.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "symbol": symbol,
                "flag_icon": flag_icon,
                "decimal_places": decimal_places,
                "is_system": True,
                "is_popular": is_popular,
            },
        )


def unseed_default_currencies(apps, schema_editor):
    Currency = apps.get_model("finance", "Currency")
    Currency.objects.filter(code__in=[item[0] for item in DEFAULT_CURRENCIES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0018_budget_notification_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="Currency",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "code",
                    models.CharField(
                        max_length=3,
                        unique=True,
                        validators=[
                            RegexValidator(
                                regex="^[A-Z]{3}$",
                                message="Код валюты должен состоять из 3 латинских букв.",
                            )
                        ],
                        verbose_name="Код валюты",
                    ),
                ),
                ("name", models.CharField(max_length=100, verbose_name="Название валюты")),
                ("symbol", models.CharField(max_length=12, verbose_name="Символ валюты")),
                (
                    "flag_icon",
                    models.CharField(default="currency", max_length=50, verbose_name="Иконка валюты"),
                ),
                (
                    "decimal_places",
                    models.PositiveSmallIntegerField(default=2, verbose_name="Количество знаков после запятой"),
                ),
                ("is_system", models.BooleanField(default=True, verbose_name="Системная валюта")),
                ("is_popular", models.BooleanField(default=False, verbose_name="Популярная валюта")),
            ],
            options={
                "verbose_name": "Валюта",
                "verbose_name_plural": "Валюты",
                "ordering": ["code"],
            },
        ),
        migrations.CreateModel(
            name="UserCurrency",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("custom_name", models.CharField(blank=True, max_length=100, verbose_name="Пользовательское название")),
                ("custom_symbol", models.CharField(blank=True, max_length=12, verbose_name="Пользовательский символ")),
                (
                    "rate_to_primary",
                    models.DecimalField(
                        decimal_places=8,
                        default=Decimal("1.00000000"),
                        max_digits=20,
                        validators=[MinValueValidator(Decimal("0.00000001"))],
                        verbose_name="Курс к основной валюте",
                    ),
                ),
                ("is_visible", models.BooleanField(default=True, verbose_name="Видима в интерфейсе")),
                ("is_primary", models.BooleanField(default=False, verbose_name="Основная валюта")),
                ("is_custom", models.BooleanField(default=False, verbose_name="Пользовательская валюта")),
                (
                    "currency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="user_settings",
                        to="finance.currency",
                        verbose_name="Валюта",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="currency_settings",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Настройка валюты пользователя",
                "verbose_name_plural": "Настройки валют пользователей",
                "ordering": ["-is_primary", "currency__code"],
            },
        ),
        migrations.AddConstraint(
            model_name="currency",
            constraint=models.CheckConstraint(
                condition=models.Q(("code__regex", "^[A-Z]{3}$")),
                name="currency_code_format",
            ),
        ),
        migrations.AddConstraint(
            model_name="currency",
            constraint=models.CheckConstraint(
                condition=models.Q(("decimal_places__gte", 0), ("decimal_places__lte", 8)),
                name="currency_decimal_places_range",
            ),
        ),
        migrations.AddIndex(
            model_name="currency",
            index=models.Index(fields=["code"], name="idx_currency_code"),
        ),
        migrations.AddIndex(
            model_name="currency",
            index=models.Index(fields=["is_system"], name="idx_currency_system"),
        ),
        migrations.AddIndex(
            model_name="currency",
            index=models.Index(fields=["is_popular"], name="idx_currency_popular"),
        ),
        migrations.AddConstraint(
            model_name="usercurrency",
            constraint=models.UniqueConstraint(fields=("user", "currency"), name="unique_user_currency_setting"),
        ),
        migrations.AddConstraint(
            model_name="usercurrency",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_primary", True)),
                fields=("user",),
                name="unique_primary_currency_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="usercurrency",
            constraint=models.CheckConstraint(
                condition=models.Q(("rate_to_primary__gt", 0)),
                name="user_currency_rate_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="usercurrency",
            index=models.Index(fields=["user"], name="idx_user_currency_user"),
        ),
        migrations.AddIndex(
            model_name="usercurrency",
            index=models.Index(fields=["user", "is_visible"], name="idx_user_currency_visible"),
        ),
        migrations.AddIndex(
            model_name="usercurrency",
            index=models.Index(fields=["user", "is_primary"], name="idx_user_currency_primary"),
        ),
        migrations.AddIndex(
            model_name="usercurrency",
            index=models.Index(fields=["user", "is_custom"], name="idx_user_currency_custom"),
        ),
        migrations.RunPython(seed_default_currencies, unseed_default_currencies),
    ]
