# Generated for BUD-1045 receipt audit logging.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0022_receipt_transaction_links"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReceiptAuditLog",
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
                    "action",
                    models.CharField(
                        choices=[
                            ("qr_parsed", "QR-код распознан"),
                            ("provider_fetch_success", "Чек получен от провайдера"),
                            ("provider_fetch_failed", "Ошибка получения от провайдера"),
                            ("duplicate_detected", "Найден дубликат"),
                            ("items_mapped", "Позиции сопоставлены"),
                            ("transactions_created", "Операции созданы"),
                            ("import_failed", "Ошибка импорта"),
                        ],
                        max_length=40,
                        verbose_name="Действие",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("success", "Успешно"),
                            ("warning", "Предупреждение"),
                            ("error", "Ошибка"),
                        ],
                        default="success",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("message", models.TextField(blank=True, verbose_name="Сообщение")),
                (
                    "qr_raw_hash",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="SHA-256 исходного QR",
                    ),
                ),
                (
                    "fiscal_key",
                    models.CharField(
                        blank=True,
                        max_length=255,
                        verbose_name="Фискальный ключ",
                    ),
                ),
                (
                    "provider_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Провайдер",
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        verbose_name="Метаданные",
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
                    "receipt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="finance.receipt",
                        verbose_name="Чек",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="receipt_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Аудит импорта чека",
                "verbose_name_plural": "Аудит импорта чеков",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="receiptauditlog",
            index=models.Index(fields=["user", "created_at"], name="idx_receipt_audit_user_time"),
        ),
        migrations.AddIndex(
            model_name="receiptauditlog",
            index=models.Index(fields=["receipt", "created_at"], name="idx_receipt_audit_receipt"),
        ),
        migrations.AddIndex(
            model_name="receiptauditlog",
            index=models.Index(fields=["action"], name="idx_receipt_audit_action"),
        ),
        migrations.AddIndex(
            model_name="receiptauditlog",
            index=models.Index(fields=["status"], name="idx_receipt_audit_status"),
        ),
    ]
