from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.common.models import TimeStampedModel


class TransactionType(models.TextChoices):
    INCOME = "income", "Доход"
    EXPENSE = "expense", "Расход"


class GoalStatus(models.TextChoices):
    ACTIVE = "active", "Активна"
    COMPLETED = "completed", "Достигнута"
    CANCELLED = "cancelled", "Отменена"


hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Цвет должен быть указан в HEX-формате, например #4F46E5.",
)


class Account(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
        verbose_name="Пользователь",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Название счёта",
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Баланс",
    )
    currency = models.CharField(
        max_length=3,
        default="RUB",
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{3}$",
                message="Валюта должна быть указана в формате ISO-кода, например RUB.",
            )
        ],
        verbose_name="Валюта",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_account_name_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="account_currency_code_format",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_account_user"),
            models.Index(fields=["user", "is_active"], name="idx_account_user_active"),
            models.Index(fields=["user", "name"], name="idx_account_user_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency})"


class Category(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name="Пользователь",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительская категория",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Название категории",
    )
    type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        verbose_name="Тип категории",
    )
    icon = models.CharField(
        max_length=50,
        default="folder",
        verbose_name="Иконка",
    )
    color = models.CharField(
        max_length=7,
        default="#64748B",
        validators=[hex_color_validator],
        verbose_name="Цвет",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок сортировки",
    )
    is_favorite = models.BooleanField(
        default=False,
        verbose_name="Избранная",
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name="Архивная",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["type", "parent_id", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name", "type"],
                name="unique_category_name_type_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=TransactionType.values),
                name="category_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(parent__isnull=True)
                    | ~models.Q(parent=models.F("id"))
                ),
                name="category_parent_not_self",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="category_color_hex_format",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_category_user"),
            models.Index(fields=["user", "type"], name="idx_category_user_type"),
            models.Index(fields=["user", "parent"], name="idx_category_user_parent"),
            models.Index(fields=["user", "is_active"], name="idx_category_user_active"),
            models.Index(fields=["user", "is_archived"], name="idx_cat_user_archived"),
            models.Index(fields=["user", "is_favorite"], name="idx_cat_user_favorite"),
            models.Index(
                fields=["user", "name", "type"],
                name="idx_category_user_name_type",
            ),
            models.Index(
                fields=["user", "type", "parent", "sort_order"],
                name="idx_cat_user_type_parent_order",
            ),
        ]

    def clean(self) -> None:
        errors = {}

        if self.parent_id:
            if self.parent_id == self.id:
                errors["parent"] = "Категория не может быть родителем самой себя."

            if self.parent.user_id != self.user_id:
                errors["parent"] = (
                    "Родительская категория должна принадлежать тому же пользователю."
                )

            if self.parent.type != self.type:
                errors["parent"] = "Родительская категория должна иметь тот же тип."

            if self._has_parent_cycle():
                errors["parent"] = "В иерархии категорий обнаружена циклическая связь."

        if errors:
            raise ValidationError(errors)

    def _has_parent_cycle(self) -> bool:
        if not self.pk:
            return False

        parent = self.parent
        visited_ids = set()

        while parent is not None:
            if parent.pk == self.pk:
                return True

            if parent.pk in visited_ids:
                return True

            visited_ids.add(parent.pk)
            parent = parent.parent

        return False

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class Transaction(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="Пользователь",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="Счёт",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="Категория",
    )
    type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        verbose_name="Тип операции",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )
    operation_date = models.DateField(
        verbose_name="Дата операции",
    )

    class Meta:
        verbose_name = "Операция"
        verbose_name_plural = "Операции"
        ordering = ["-operation_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="transaction_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=TransactionType.values),
                name="transaction_type_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_transaction_user"),
            models.Index(
                fields=["user", "operation_date"],
                name="idx_transaction_user_date",
            ),
            models.Index(
                fields=["user", "account", "operation_date"],
                name="idx_tx_user_acct_date",
            ),
            models.Index(
                fields=["user", "category", "operation_date"],
                name="idx_tx_user_cat_date",
            ),
            models.Index(
                fields=["user", "type", "operation_date"],
                name="idx_tx_user_type_date",
            ),
            models.Index(
                fields=["user", "amount"],
                name="idx_tx_user_amount",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="idx_tx_user_created",
            ),
        ]

    def clean(self) -> None:
        errors = {}

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт должен принадлежать пользователю операции."

        if self.category_id and self.user_id and self.category.user_id != self.user_id:
            errors["category"] = "Категория должна принадлежать пользователю операции."

        if self.category_id and self.type and self.category.type != self.type:
            errors["category"] = "Тип категории должен совпадать с типом операции."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.type}: {self.amount} {self.account.currency}"


class Budget(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgets",
        verbose_name="Пользователь",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name="Категория",
    )
    amount_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Лимит бюджета",
    )
    period_start = models.DateField(
        verbose_name="Начало периода",
    )
    period_end = models.DateField(
        verbose_name="Конец периода",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Бюджет"
        verbose_name_plural = "Бюджеты"
        ordering = ["-period_start", "category"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_limit__gt=0),
                name="budget_amount_limit_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="budget_period_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "category", "period_start", "period_end"],
                name="unique_budget_category_period_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_budget_user"),
            models.Index(
                fields=["user", "period_start", "period_end"],
                name="idx_budget_user_period",
            ),
            models.Index(
                fields=["user", "category", "period_start", "period_end"],
                name="idx_budget_user_cat_period",
            ),
            models.Index(fields=["user", "is_active"], name="idx_budget_user_active"),
        ]

    def clean(self) -> None:
        errors = {}

        if self.period_start and self.period_end and self.period_end < self.period_start:
            errors["period_end"] = (
                "Дата окончания периода не может быть раньше даты начала."
            )

        if self.category_id and self.user_id and self.category.user_id != self.user_id:
            errors["category"] = "Категория бюджета должна принадлежать пользователю."

        if self.category_id and self.category.type != TransactionType.EXPENSE:
            errors["category"] = (
                "Бюджет можно создавать только для категории расходов."
            )

        if self.category_id and not self.category.is_active:
            errors["category"] = "Нельзя использовать неактивную категорию в бюджете."

        if self.category_id and self.category.is_archived:
            errors["category"] = "Нельзя использовать архивную категорию в бюджете."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.category.name}: {self.amount_limit}"


class Goal(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goals",
        verbose_name="Пользователь",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goals",
        verbose_name="Связанный счёт",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Название цели",
    )
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Целевая сумма",
    )
    current_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Текущая сумма",
    )
    deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name="Срок достижения",
    )
    status = models.CharField(
        max_length=20,
        choices=GoalStatus.choices,
        default=GoalStatus.ACTIVE,
        verbose_name="Статус",
    )

    class Meta:
        verbose_name = "Финансовая цель"
        verbose_name_plural = "Финансовые цели"
        ordering = ["status", "deadline", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_amount__gt=0),
                name="goal_target_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(current_amount__gte=0),
                name="goal_current_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=GoalStatus.values),
                name="goal_status_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_goal_name_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_goal_user"),
            models.Index(fields=["user", "status"], name="idx_goal_user_status"),
            models.Index(fields=["user", "deadline"], name="idx_goal_user_deadline"),
            models.Index(fields=["user", "account"], name="idx_goal_user_account"),
        ]

    def clean(self) -> None:
        errors = {}

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт цели должен принадлежать пользователю."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name}: {self.current_amount}/{self.target_amount}"