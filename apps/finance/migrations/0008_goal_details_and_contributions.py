# Generated manually for BUD-1078

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_account_details_and_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="goal",
            name="category",
            field=models.CharField(
                choices=[
                    ("savings", "Накопления"),
                    ("housing", "Жильё"),
                    ("transport", "Транспорт"),
                    ("travel", "Путешествия"),
                    ("other", "Другое"),
                ],
                default="savings",
                max_length=20,
                verbose_name="Категория цели",
            ),
        ),
        migrations.AddField(
            model_name="goal",
            name="priority",
            field=models.CharField(
                choices=[
                    ("high", "Высокий"),
                    ("medium", "Средний"),
                    ("low", "Низкий"),
                ],
                default="medium",
                max_length=20,
                verbose_name="Приоритет",
            ),
        ),
        migrations.AddField(
            model_name="goal",
            name="icon",
            field=models.CharField(
                default="target",
                max_length=50,
                verbose_name="Иконка",
            ),
        ),
        migrations.AddField(
            model_name="goal",
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
            model_name="goal",
            name="comment",
            field=models.TextField(
                blank=True,
                verbose_name="Комментарий",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="goal",
            name="goal_status_valid",
        ),
        migrations.AlterField(
            model_name="goal",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Активна"),
                    ("completed", "Завершена"),
                    ("archived", "В архиве"),
                    ("cancelled", "Отменена"),
                ],
                default="active",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.AddConstraint(
            model_name="goal",
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=[
                    "active",
                    "completed",
                    "archived",
                    "cancelled",
                ]),
                name="goal_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="goal",
            constraint=models.CheckConstraint(
                condition=models.Q(category__in=[
                    "savings",
                    "housing",
                    "transport",
                    "travel",
                    "other",
                ]),
                name="goal_category_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="goal",
            constraint=models.CheckConstraint(
                condition=models.Q(priority__in=[
                    "high",
                    "medium",
                    "low",
                ]),
                name="goal_priority_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="goal",
            constraint=models.CheckConstraint(
                condition=models.Q(color__regex="^#[0-9A-Fa-f]{6}$"),
                name="goal_color_hex_format",
            ),
        ),
        migrations.AddIndex(
            model_name="goal",
            index=models.Index(
                fields=["user", "category"],
                name="idx_goal_user_category",
            ),
        ),
        migrations.AddIndex(
            model_name="goal",
            index=models.Index(
                fields=["user", "priority"],
                name="idx_goal_user_priority",
            ),
        ),
        migrations.AddIndex(
            model_name="goal",
            index=models.Index(
                fields=["user", "status", "deadline"],
                name="idx_goal_user_status_deadline",
            ),
        ),
        migrations.CreateModel(
            name="GoalContribution",
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
                    "account_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Название счёта на момент пополнения",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        validators=[
                            django.core.validators.MinValueValidator(
                                Decimal("0.01"),
                            ),
                        ],
                        verbose_name="Сумма пополнения",
                    ),
                ),
                (
                    "contribution_date",
                    models.DateField(verbose_name="Дата пополнения"),
                ),
                (
                    "comment",
                    models.TextField(blank=True, verbose_name="Комментарий"),
                ),
                (
                    "account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="goal_contributions",
                        to="finance.account",
                        verbose_name="Счёт-источник",
                    ),
                ),
                (
                    "goal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="contributions",
                        to="finance.goal",
                        verbose_name="Цель",
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="goal_contributions",
                        to="finance.transaction",
                        verbose_name="Связанная операция",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="goal_contributions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Пополнение цели",
                "verbose_name_plural": "Пополнения целей",
                "ordering": ["-contribution_date", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="goalcontribution",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="goal_contribution_amount_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="goalcontribution",
            index=models.Index(
                fields=["user"],
                name="idx_gcontrib_user",
            ),
        ),
        migrations.AddIndex(
            model_name="goalcontribution",
            index=models.Index(
                fields=["goal", "contribution_date"],
                name="idx_gcontrib_goal_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="goalcontribution",
            index=models.Index(
                fields=["user", "goal", "contribution_date"],
                name="idx_gcontrib_user_goal_dt",
            ),
        ),
        migrations.AddIndex(
            model_name="goalcontribution",
            index=models.Index(
                fields=["account"],
                name="idx_gcontrib_account",
            ),
        ),
        migrations.AddIndex(
            model_name="goalcontribution",
            index=models.Index(
                fields=["transaction"],
                name="idx_gcontrib_tx",
            ),
        ),
    ]
