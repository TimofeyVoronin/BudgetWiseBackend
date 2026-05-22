# Generated for BUD-1043 receipt duplicate prevention.

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0019_currencies"),
    ]

    operations = [
        migrations.CreateModel(
            name="Receipt",
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
                ("qr_raw", models.TextField(verbose_name="Исходная строка QR-кода")),
                ("raw_hash", models.CharField(max_length=64, verbose_name="SHA-256 исходного QR")),
                ("deduplication_key", models.CharField(max_length=255, verbose_name="Ключ защиты от дублей")),
                ("fiscal_key", models.CharField(max_length=255, verbose_name="Фискальный ключ")),
                ("fiscal_drive_number", models.CharField(max_length=32, verbose_name="ФН")),
                ("fiscal_document_number", models.CharField(max_length=32, verbose_name="ФД")),
                ("fiscal_sign", models.CharField(max_length=32, verbose_name="ФПД")),
                ("operation_type_code", models.CharField(max_length=1, verbose_name="Код типа операции")),
                (
                    "operation_type",
                    models.CharField(
                        choices=[
                            ("income", "Приход"),
                            ("income_return", "Возврат прихода"),
                            ("expense", "Расход"),
                            ("expense_return", "Возврат расхода"),
                        ],
                        max_length=30,
                        verbose_name="Тип операции по чеку",
                    ),
                ),
                ("receipt_datetime", models.DateTimeField(verbose_name="Дата и время чека")),
                (
                    "total_amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.01"))],
                        verbose_name="Сумма чека",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("parsed", "Распознан"),
                            ("fetched", "Получен от провайдера"),
                            ("imported", "Импортирован"),
                            ("duplicate", "Дубликат"),
                            ("error", "Ошибка"),
                        ],
                        default="parsed",
                        max_length=20,
                        verbose_name="Статус импорта чека",
                    ),
                ),
                ("provider_name", models.CharField(blank=True, max_length=100, verbose_name="Провайдер")),
                ("provider_code", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Код ответа провайдера")),
                ("store_name", models.CharField(blank=True, max_length=255, verbose_name="Магазин")),
                ("seller_inn", models.CharField(blank=True, max_length=20, verbose_name="ИНН продавца")),
                ("provider_payload", models.JSONField(blank=True, default=dict, verbose_name="Сырой ответ провайдера")),
                ("note", models.TextField(blank=True, verbose_name="Комментарий")),
                (
                    "duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duplicate_attempts",
                        to="finance.receipt",
                        verbose_name="Дубликат чека",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipts",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Импортированный чек",
                "verbose_name_plural": "Импортированные чеки",
                "ordering": ["-receipt_datetime", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.UniqueConstraint(
                fields=("user", "deduplication_key"),
                name="unique_receipt_dedup_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.CheckConstraint(
                condition=models.Q(("total_amount__gt", 0)),
                name="receipt_total_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.CheckConstraint(
                condition=models.Q(("operation_type__in", ["income", "income_return", "expense", "expense_return"])),
                name="receipt_operation_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["parsed", "fetched", "imported", "duplicate", "error"])),
                name="receipt_status_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["user"], name="idx_receipt_user"),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["user", "raw_hash"], name="idx_receipt_user_hash"),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["user", "fiscal_key"], name="idx_receipt_user_fiscal"),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["user", "receipt_datetime"], name="idx_receipt_user_date"),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["user", "status"], name="idx_receipt_user_status"),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(fields=["seller_inn"], name="idx_receipt_seller_inn"),
        ),
    ]
