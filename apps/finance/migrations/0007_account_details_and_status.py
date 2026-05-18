# Generated manually for BUD-1074

from decimal import Decimal

import django.core.validators
from django.conf import settings
from django.db import migrations, models


def copy_current_balance_to_initial_balance(apps, schema_editor):
    Account = apps.get_model("finance", "Account")
    for account in Account.objects.all().only("id", "balance"):
        account.initial_balance = account.balance
        account.save(update_fields=["initial_balance"])


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0006_category_search_filter_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="account",
            options={
                "ordering": ["-is_default", "is_archived", "name"],
                "verbose_name": "Счёт",
                "verbose_name_plural": "Счета",
            },
        ),
        migrations.AddField(
            model_name="account",
            name="type",
            field=models.CharField(
                choices=[
                    ("card", "Банковская карта"),
                    ("debit", "Дебетовая карта"),
                    ("savings", "Накопительный"),
                    ("cash", "Наличные"),
                    ("credit", "Кредитный"),
                    ("other", "Другое"),
                ],
                default="card",
                max_length=20,
                verbose_name="Тип счёта",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="bank_name",
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name="Банк",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="initial_balance",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                ],
                verbose_name="Начальный баланс",
            ),
        ),
        migrations.AlterField(
            model_name="account",
            name="balance",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                verbose_name="Текущий баланс",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="blocked_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                ],
                verbose_name="Заблокированная сумма",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="credit_limit",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                ],
                verbose_name="Кредитный лимит",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="icon",
            field=models.CharField(
                default="card",
                max_length=50,
                verbose_name="Иконка",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="color",
            field=models.CharField(
                default="#4F46E5",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Цвет должен быть указан в HEX-формате, например #4F46E5.",
                        regex="^#[0-9A-Fa-f]{6}$",
                    ),
                ],
                verbose_name="Цвет",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="is_default",
            field=models.BooleanField(
                default=False,
                verbose_name="Счёт по умолчанию",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="is_archived",
            field=models.BooleanField(
                default=False,
                verbose_name="Архивный",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="comment",
            field=models.TextField(
                blank=True,
                verbose_name="Комментарий",
            ),
        ),
        migrations.RunPython(
            copy_current_balance_to_initial_balance,
            migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["user", "is_archived"],
                name="idx_account_user_archived",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["user", "is_default"],
                name="idx_account_user_default",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["user", "type"],
                name="idx_account_user_type",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["user", "currency"],
                name="idx_account_user_currency",
            ),
        ),
        migrations.AddIndex(
            model_name="account",
            index=models.Index(
                fields=["user", "type", "is_active", "is_archived"],
                name="idx_account_type_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(is_default=True),
                name="unique_default_account_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(type__in=["card", "debit", "savings", "cash", "credit", "other"]),
                name="account_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(color__regex="^#[0-9A-Fa-f]{6}$"),
                name="account_color_hex_format",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(initial_balance__gte=0),
                name="account_initial_balance_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(blocked_amount__gte=0),
                name="account_blocked_amount_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.CheckConstraint(
                condition=models.Q(credit_limit__gte=0),
                name="account_credit_limit_non_negative",
            ),
        ),
    ]
