# Generated manually for BUD-1158 recommendation storage models.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0028_formula_ide_draft"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialRecommendation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("code", models.CharField(max_length=80, verbose_name="Код рекомендации")),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("budget", "Бюджет"),
                            ("saving", "Сбережения"),
                            ("goal", "Цель"),
                            ("cashflow", "Денежный поток"),
                            ("planned_payment", "Планируемый платёж"),
                            ("expense_stability", "Стабильность расходов"),
                            ("onboarding", "Онбординг"),
                            ("financial_health", "Финансовое здоровье"),
                        ],
                        max_length=40,
                        verbose_name="Тип рекомендации",
                    ),
                ),
                (
                    "priority",
                    models.CharField(
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
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "Новая"),
                            ("active", "Активная"),
                            ("accepted", "Принята"),
                            ("hidden", "Скрыта"),
                            ("snoozed", "Отложена"),
                            ("expired", "Истекла"),
                        ],
                        default="active",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="Заголовок")),
                ("text", models.TextField(verbose_name="Текст рекомендации")),
                ("action", models.TextField(blank=True, verbose_name="Предлагаемое действие")),
                ("reason", models.TextField(blank=True, verbose_name="Причина появления")),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("financial_health", "Финансовое здоровье"),
                            ("budgets", "Бюджеты"),
                            ("goals", "Цели"),
                            ("transactions", "Операции"),
                            ("planned_transactions", "Планируемые операции"),
                            ("onboarding", "Онбординг"),
                        ],
                        max_length=60,
                        verbose_name="Источник данных",
                    ),
                ),
                (
                    "source_key",
                    models.CharField(
                        blank=True,
                        help_text="Используется для защиты от дублей при повторной генерации.",
                        max_length=120,
                        verbose_name="Ключ источника",
                    ),
                ),
                ("context", models.JSONField(blank=True, default=dict, verbose_name="Контекст рекомендации")),
                ("expires_at", models.DateTimeField(blank=True, null=True, verbose_name="Актуальна до")),
                ("snoozed_until", models.DateTimeField(blank=True, null=True, verbose_name="Отложена до")),
                ("accepted_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата принятия")),
                ("hidden_at", models.DateTimeField(blank=True, null=True, verbose_name="Дата скрытия")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_recommendations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Финансовая рекомендация",
                "verbose_name_plural": "Финансовые рекомендации",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="FinancialRecommendationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("created", "Создана"),
                            ("viewed", "Просмотрена"),
                            ("accepted", "Принята"),
                            ("hidden", "Скрыта"),
                            ("snoozed", "Отложена"),
                            ("expired", "Истекла"),
                            ("refreshed", "Обновлена"),
                        ],
                        max_length=30,
                        verbose_name="Тип события",
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict, verbose_name="Метаданные события")),
                (
                    "recommendation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="finance.financialrecommendation",
                        verbose_name="Рекомендация",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_recommendation_events",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Событие финансовой рекомендации",
                "verbose_name_plural": "События финансовых рекомендаций",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="financialrecommendation",
            constraint=models.CheckConstraint(
                condition=models.Q(("type__in", [
                    "budget",
                    "saving",
                    "goal",
                    "cashflow",
                    "planned_payment",
                    "expense_stability",
                    "onboarding",
                    "financial_health",
                ])),
                name="fin_rec_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="financialrecommendation",
            constraint=models.CheckConstraint(
                condition=models.Q(("priority__in", ["high", "medium", "low"])),
                name="fin_rec_priority_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="financialrecommendation",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["new", "active", "accepted", "hidden", "snoozed", "expired"])),
                name="fin_rec_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="financialrecommendation",
            constraint=models.CheckConstraint(
                condition=models.Q(("source__in", [
                    "financial_health",
                    "budgets",
                    "goals",
                    "transactions",
                    "planned_transactions",
                    "onboarding",
                ])),
                name="fin_rec_source_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="financialrecommendation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["new", "active", "snoozed"])),
                fields=("user", "code", "source", "source_key"),
                name="uniq_fin_rec_active_rule",
            ),
        ),
        migrations.AddConstraint(
            model_name="financialrecommendationevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("event_type__in", [
                    "created",
                    "viewed",
                    "accepted",
                    "hidden",
                    "snoozed",
                    "expired",
                    "refreshed",
                ])),
                name="fin_rec_event_type_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="financialrecommendation",
            index=models.Index(fields=["user", "status"], name="idx_fin_rec_user_status"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendation",
            index=models.Index(fields=["user", "priority"], name="idx_fin_rec_user_prio"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendation",
            index=models.Index(fields=["user", "type"], name="idx_fin_rec_user_type"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendation",
            index=models.Index(fields=["user", "expires_at"], name="idx_fin_rec_user_expires"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendation",
            index=models.Index(fields=["code"], name="idx_fin_rec_code"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendationevent",
            index=models.Index(fields=["recommendation", "created_at"], name="idx_fin_rec_event_rec"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendationevent",
            index=models.Index(fields=["user", "event_type"], name="idx_fin_rec_event_user_type"),
        ),
        migrations.AddIndex(
            model_name="financialrecommendationevent",
            index=models.Index(fields=["user", "created_at"], name="idx_fin_rec_event_user_date"),
        ),
    ]
