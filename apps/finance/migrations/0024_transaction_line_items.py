# Generated for transaction line items in regular operations.

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0023_receipt_audit_logs"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransactionLineItem",
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
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="Дата создания",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="Дата обновления",
                    ),
                ),
                (
                    "line_number",
                    models.PositiveIntegerField(
                        verbose_name="Номер строки",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=255,
                        verbose_name="Название позиции",
                    ),
                ),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=3,
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.001"))],
                        verbose_name="Количество",
                    ),
                ),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.00"))],
                        verbose_name="Цена за единицу",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.01"))],
                        verbose_name="Сумма позиции",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="line_items",
                        to="finance.transaction",
                        verbose_name="Операция",
                    ),
                ),
            ],
            options={
                "verbose_name": "Позиция операции",
                "verbose_name_plural": "Позиции операций",
                "ordering": ["transaction", "line_number"],
            },
        ),
        migrations.AddConstraint(
            model_name="transactionlineitem",
            constraint=models.UniqueConstraint(
                fields=("transaction", "line_number"),
                name="unique_transaction_line_item",
            ),
        ),
        migrations.AddConstraint(
            model_name="transactionlineitem",
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="transaction_line_item_quantity_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="transactionlineitem",
            constraint=models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="transaction_line_item_unit_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="transactionlineitem",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="transaction_line_item_amount_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="transactionlineitem",
            index=models.Index(fields=["transaction"], name="idx_tx_line_item_tx"),
        ),
        migrations.AddIndex(
            model_name="transactionlineitem",
            index=models.Index(fields=["name"], name="idx_tx_line_item_name"),
        ),
    ]
