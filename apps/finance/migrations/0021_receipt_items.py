# Generated for BUD-1042 receipt item mapping.

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0020_receipts"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReceiptItem",
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
                ("line_number", models.PositiveIntegerField(verbose_name="Номер строки")),
                ("name", models.CharField(max_length=255, verbose_name="Название позиции")),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=3,
                        default=Decimal("0.000"),
                        max_digits=12,
                        validators=[MinValueValidator(Decimal("0.000"))],
                        verbose_name="Количество",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.00"))],
                        verbose_name="Цена",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.00"))],
                        verbose_name="Сумма",
                    ),
                ),
                (
                    "mapping_confidence",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=4,
                        validators=[MinValueValidator(Decimal("0.00"))],
                        verbose_name="Уверенность сопоставления",
                    ),
                ),
                ("mapping_reason", models.CharField(blank=True, max_length=255, verbose_name="Причина сопоставления")),
                ("provider_payload", models.JSONField(blank=True, default=dict, verbose_name="Сырой объект позиции от провайдера")),
                (
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="finance.receipt",
                        verbose_name="Чек",
                    ),
                ),
                (
                    "suggested_category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="suggested_receipt_items",
                        to="finance.category",
                        verbose_name="Предложенная категория",
                    ),
                ),
            ],
            options={
                "verbose_name": "Позиция чека",
                "verbose_name_plural": "Позиции чеков",
                "ordering": ["receipt", "line_number"],
            },
        ),
        migrations.AddConstraint(
            model_name="receiptitem",
            constraint=models.UniqueConstraint(
                fields=("receipt", "line_number"),
                name="unique_receipt_item_line",
            ),
        ),
        migrations.AddConstraint(
            model_name="receiptitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gte", 0)),
                name="receipt_item_quantity_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="receiptitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("price__gte", 0)),
                name="receipt_item_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="receiptitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gte", 0)),
                name="receipt_item_amount_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="receiptitem",
            constraint=models.CheckConstraint(
                condition=(models.Q(("mapping_confidence__gte", 0)) & models.Q(("mapping_confidence__lte", 1))),
                name="receipt_item_mapping_confidence_range",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(fields=["receipt"], name="idx_receipt_item_receipt"),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(fields=["suggested_category"], name="idx_receipt_item_category"),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(fields=["receipt", "suggested_category"], name="idx_receipt_item_receipt_cat"),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(fields=["name"], name="idx_receipt_item_name"),
        ),
    ]
