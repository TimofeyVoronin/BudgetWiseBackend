# Generated manually for BUD-1082 notifications center.

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_goal_details_and_contributions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                    "title",
                    models.CharField(
                        max_length=200,
                        verbose_name="Заголовок уведомления",
                    ),
                ),
                (
                    "body",
                    models.TextField(
                        blank=True,
                        verbose_name="Текст уведомления",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("operation", "Операции"),
                            ("goal", "Цели"),
                            ("budget", "Бюджет"),
                            ("system", "Система"),
                            ("security", "Безопасность"),
                        ],
                        default="system",
                        max_length=20,
                        verbose_name="Тип уведомления",
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("in_app", "In-app"),
                            ("email", "Email"),
                            ("push", "Push"),
                            ("sms", "SMS"),
                        ],
                        default="in_app",
                        max_length=20,
                        verbose_name="Канал доставки",
                    ),
                ),
                (
                    "delivery_status",
                    models.CharField(
                        choices=[
                            ("delivered", "Доставлено"),
                            ("failed", "Ошибка доставки"),
                            ("pending", "Ожидает доставки"),
                            ("unavailable", "Канал недоступен"),
                        ],
                        default="delivered",
                        max_length=20,
                        verbose_name="Статус доставки",
                    ),
                ),
                (
                    "delivery_error",
                    models.TextField(
                        blank=True,
                        verbose_name="Ошибка доставки",
                    ),
                ),
                (
                    "icon",
                    models.CharField(
                        default="bell",
                        max_length=50,
                        verbose_name="Иконка",
                    ),
                ),
                (
                    "icon_tone",
                    models.CharField(
                        choices=[
                            ("primary", "Основной"),
                            ("success", "Успех"),
                            ("warning", "Предупреждение"),
                            ("error", "Ошибка"),
                            ("info", "Информация"),
                        ],
                        default="primary",
                        max_length=20,
                        verbose_name="Тон иконки",
                    ),
                ),
                (
                    "is_read",
                    models.BooleanField(
                        default=False,
                        verbose_name="Прочитано",
                    ),
                ),
                (
                    "read_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Дата прочтения",
                    ),
                ),
                (
                    "is_archived",
                    models.BooleanField(
                        default=False,
                        verbose_name="В архиве",
                    ),
                ),
                (
                    "archived_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Дата архивации",
                    ),
                ),
                (
                    "entity_kind",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("transaction", "Операция"),
                            ("goal", "Цель"),
                            ("budget", "Бюджет"),
                        ],
                        max_length=20,
                        verbose_name="Тип связанной сущности",
                    ),
                ),
                (
                    "entity_id",
                    models.PositiveBigIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="ID связанной сущности",
                    ),
                ),
                (
                    "entity_route_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Маршрут связанной сущности",
                    ),
                ),
                (
                    "entity_label",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="Название связанной сущности",
                    ),
                ),
                (
                    "entity_tag",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="Тег связанной сущности",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        verbose_name="Сумма",
                    ),
                ),
                (
                    "account_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Название счёта",
                    ),
                ),
                (
                    "category_name",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        verbose_name="Название категории",
                    ),
                ),
                (
                    "related_goal_name",
                    models.CharField(
                        blank=True,
                        max_length=150,
                        verbose_name="Название связанной цели",
                    ),
                ),
                (
                    "related_goal_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=5,
                        null=True,
                        verbose_name="Процент связанной цели",
                    ),
                ),
                (
                    "delivery_steps",
                    models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Шаги доставки",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Уведомление",
                "verbose_name_plural": "Уведомления",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(("type__in", ["operation", "goal", "budget", "system", "security"])),
                name="notification_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(("channel__in", ["in_app", "email", "push", "sms"])),
                name="notification_channel_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(("delivery_status__in", ["delivered", "failed", "pending", "unavailable"])),
                name="notif_delivery_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(("icon_tone__in", ["primary", "success", "warning", "error", "info"])),
                name="notif_icon_tone_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("entity_kind", ""))
                    | models.Q(("entity_kind__in", ["transaction", "goal", "budget"]))
                ),
                name="notif_entity_kind_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user"], name="idx_notif_user"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "is_read"], name="idx_notif_user_read"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "is_archived"], name="idx_notif_user_archived"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "type"], name="idx_notif_user_type"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "channel"], name="idx_notif_user_channel"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "created_at"], name="idx_notif_user_created"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "entity_kind", "entity_id"], name="idx_notif_entity"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["user", "delivery_status"], name="idx_notif_delivery"),
        ),
    ]
