import re
from datetime import time
from decimal import Decimal

from django.utils import timezone
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
    COMPLETED = "completed", "Завершена"
    ARCHIVED = "archived", "В архиве"
    CANCELLED = "cancelled", "Отменена"


class GoalPriority(models.TextChoices):
    HIGH = "high", "Высокий"
    MEDIUM = "medium", "Средний"
    LOW = "low", "Низкий"


class GoalCategory(models.TextChoices):
    SAVINGS = "savings", "Накопления"
    HOUSING = "housing", "Жильё"
    TRANSPORT = "transport", "Транспорт"
    TRAVEL = "travel", "Путешествия"
    OTHER = "other", "Другое"


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", "In-app"
    EMAIL = "email", "Email"
    PUSH = "push", "Push"
    SMS = "sms", "SMS"


class NotificationType(models.TextChoices):
    OPERATION = "operation", "Операции"
    GOAL = "goal", "Цели"
    BUDGET = "budget", "Бюджет"
    SYSTEM = "system", "Система"
    SECURITY = "security", "Безопасность"
    MARKETING = "marketing", "Маркетинг и акции"


class NotificationDeliveryStatus(models.TextChoices):
    DELIVERED = "delivered", "Доставлено"
    FAILED = "failed", "Ошибка доставки"
    PENDING = "pending", "Ожидает доставки"
    UNAVAILABLE = "unavailable", "Канал недоступен"


class NotificationIconTone(models.TextChoices):
    PRIMARY = "primary", "Основной"
    SUCCESS = "success", "Успех"
    WARNING = "warning", "Предупреждение"
    ERROR = "error", "Ошибка"
    INFO = "info", "Информация"


class NotificationEntityKind(models.TextChoices):
    TRANSACTION = "transaction", "Операция"
    GOAL = "goal", "Цель"
    BUDGET = "budget", "Бюджет"


class RecurringFrequency(models.TextChoices):
    DAILY = "daily", "Ежедневно"
    WEEKLY = "weekly", "Еженедельно"
    MONTHLY = "monthly", "Ежемесячно"
    YEARLY = "yearly", "Ежегодно"


class RecurringStatus(models.TextChoices):
    ACTIVE = "active", "Активна"
    PAUSED = "paused", "На паузе"
    COMPLETED = "completed", "Завершена"
    ERROR = "error", "Ошибка"


class RecurringChargeStatus(models.TextChoices):
    SUCCESS = "success", "Выполнено"
    FAILED = "failed", "Ошибка"
    SKIPPED = "skipped", "Пропущено"


class PlannedStatus(models.TextChoices):
    PENDING = "pending", "Ожидает"
    CONFIRMED = "confirmed", "Подтверждена"
    CANCELLED = "cancelled", "Отменена"
    CONVERTED = "converted", "Конвертирована"
    OVERDUE = "overdue", "Просрочена"


class BudgetKind(models.TextChoices):
    EXPENSE = "expense", "Расходный"
    INCOME = "income", "Доходный"


class BudgetPeriodType(models.TextChoices):
    MONTH = "month", "Месяц"
    QUARTER = "quarter", "Квартал"
    YEAR = "year", "Год"


class BudgetCategoryGroup(models.TextChoices):
    MAIN = "main", "Основной бюджет"
    FAMILY = "family", "Семейный"
    PERSONAL = "personal", "Личный"


class BudgetUsageStatus(models.TextChoices):
    NORMAL = "normal", "Норма"
    WARNING = "warning", "Близко к лимиту"
    EXCEEDED = "exceeded", "Превышен"


NOTIFICATION_QUIET_HOURS_DAYS = {
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
}


def default_quiet_hours_days() -> list[str]:
    return ["mon", "tue", "wed", "thu", "fri"]


class AccountType(models.TextChoices):
    CARD = "card", "Банковская карта"
    DEBIT = "debit", "Дебетовая карта"
    SAVINGS = "savings", "Накопительный"
    CASH = "cash", "Наличные"
    CREDIT = "credit", "Кредитный"
    OTHER = "other", "Другое"


hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Цвет должен быть указан в HEX-формате, например #4F46E5.",
)


def normalize_tag_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


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
    type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.CARD,
        verbose_name="Тип счёта",
    )
    bank_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Банк",
    )
    initial_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Начальный баланс",
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Текущий баланс",
    )
    blocked_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Заблокированная сумма",
    )
    credit_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Кредитный лимит",
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
    icon = models.CharField(
        max_length=50,
        default="card",
        verbose_name="Иконка",
    )
    color = models.CharField(
        max_length=7,
        default="#4F46E5",
        validators=[hex_color_validator],
        verbose_name="Цвет",
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Счёт по умолчанию",
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name="Архивный",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["-is_default", "is_archived", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_account_name_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="unique_default_account_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=AccountType.values),
                name="account_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="account_currency_code_format",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="account_color_hex_format",
            ),
            models.CheckConstraint(
                condition=models.Q(initial_balance__gte=0),
                name="account_initial_balance_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(blocked_amount__gte=0),
                name="account_blocked_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(credit_limit__gte=0),
                name="account_credit_limit_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_account_user"),
            models.Index(fields=["user", "is_active"], name="idx_account_user_active"),
            models.Index(fields=["user", "is_archived"], name="idx_account_user_archived"),
            models.Index(fields=["user", "is_default"], name="idx_account_user_default"),
            models.Index(fields=["user", "type"], name="idx_account_user_type"),
            models.Index(fields=["user", "currency"], name="idx_account_user_currency"),
            models.Index(fields=["user", "name"], name="idx_account_user_name"),
            models.Index(
                fields=["user", "type", "is_active", "is_archived"],
                name="idx_account_type_status",
            ),
        ]

    @property
    def status(self) -> str:
        if self.is_archived:
            return "archived"

        return "active"

    @property
    def available_balance(self) -> Decimal:
        return self.balance - self.blocked_amount + self.credit_limit

    def clean(self) -> None:
        errors = {}

        if self.currency:
            self.currency = self.currency.upper()

        if self.type not in AccountType.values:
            errors["type"] = "Недопустимый тип счёта."

        if self.is_archived:
            self.is_active = False
            self.is_default = False

        if self.blocked_amount < Decimal("0.00"):
            errors["blocked_amount"] = "Заблокированная сумма не может быть отрицательной."

        if self.credit_limit < Decimal("0.00"):
            errors["credit_limit"] = "Кредитный лимит не может быть отрицательным."

        if errors:
            raise ValidationError(errors)

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
                fields=["user", "type", "name"],
                name="idx_cat_user_type_name",
            ),
            models.Index(
                fields=["user", "type", "is_active", "is_archived", "is_favorite"],
                name="idx_cat_user_type_flags",
            ),
            models.Index(
                fields=[
                    "user",
                    "type",
                    "parent",
                    "is_active",
                    "is_archived",
                    "is_favorite",
                    "sort_order",
                ],
                name="idx_cat_tree_flags_order",
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


class TagGroup(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tag_groups",
        verbose_name="Пользователь",
    )
    name = models.CharField(
        max_length=80,
        verbose_name="Название группы тегов",
    )
    normalized_name = models.CharField(
        max_length=80,
        blank=True,
        editable=False,
        verbose_name="Нормализованное название группы",
    )
    is_system = models.BooleanField(
        default=False,
        verbose_name="Системная группа",
    )

    class Meta:
        verbose_name = "Группа тегов"
        verbose_name_plural = "Группы тегов"
        ordering = ["is_system", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="tag_group_name_not_blank",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_system=True, user__isnull=True)
                    | models.Q(is_system=False, user__isnull=False)
                ),
                name="tag_group_owner_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "normalized_name"],
                condition=models.Q(user__isnull=False),
                name="unique_tag_group_name_per_user",
            ),
            models.UniqueConstraint(
                fields=["normalized_name"],
                condition=models.Q(is_system=True),
                name="unique_system_tag_group_name",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "name"], name="idx_tag_group_user_name"),
            models.Index(fields=["user", "is_system"], name="idx_tag_group_user_system"),
        ]

    def clean(self) -> None:
        errors = {}

        self.name = self.name.strip()
        self.normalized_name = normalize_tag_text(self.name)

        if not self.name:
            errors["name"] = "Название группы тегов не может быть пустым."

        if self.is_system and self.user_id is not None:
            errors["user"] = "Системная группа тегов не должна быть привязана к пользователю."

        if not self.is_system and self.user_id is None:
            errors["user"] = "Пользовательская группа тегов должна быть привязана к пользователю."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.normalized_name = normalize_tag_text(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Tag(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tags",
        verbose_name="Пользователь",
    )
    group = models.ForeignKey(
        TagGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tags",
        verbose_name="Группа тегов",
    )
    name = models.CharField(
        max_length=80,
        verbose_name="Название тега",
    )
    normalized_name = models.CharField(
        max_length=80,
        blank=True,
        editable=False,
        verbose_name="Нормализованное название тега",
    )
    color = models.CharField(
        max_length=7,
        default="#4F46E5",
        validators=[hex_color_validator],
        verbose_name="Цвет",
    )
    icon = models.CharField(
        max_length=50,
        default="tag",
        verbose_name="Иконка",
    )
    is_visible = models.BooleanField(
        default=True,
        verbose_name="Показывать в формах операций",
    )
    is_system = models.BooleanField(
        default=False,
        verbose_name="Системный тег",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )

    class Meta:
        verbose_name = "Тег операции"
        verbose_name_plural = "Теги операций"
        ordering = ["is_system", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(name__regex=r"\S"),
                name="tag_name_not_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="tag_color_hex_format",
            ),
            models.CheckConstraint(
                condition=models.Q(icon__regex=r"\S"),
                name="tag_icon_not_blank",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_system=True, user__isnull=True)
                    | models.Q(is_system=False, user__isnull=False)
                ),
                name="tag_owner_valid",
            ),
            models.UniqueConstraint(
                fields=["user", "normalized_name"],
                condition=models.Q(user__isnull=False),
                name="unique_tag_name_per_user",
            ),
            models.UniqueConstraint(
                fields=["normalized_name"],
                condition=models.Q(is_system=True),
                name="unique_system_tag_name",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_tag_user"),
            models.Index(fields=["user", "group"], name="idx_tag_user_group"),
            models.Index(fields=["user", "is_visible"], name="idx_tag_user_visible"),
            models.Index(fields=["user", "normalized_name"], name="idx_tag_user_norm_name"),
            models.Index(fields=["user", "created_at"], name="idx_tag_user_created"),
            models.Index(fields=["is_system"], name="idx_tag_system"),
        ]

    def clean(self) -> None:
        errors = {}

        self.name = self.name.strip()
        self.icon = self.icon.strip()
        self.color = self.color.upper()
        self.normalized_name = normalize_tag_text(self.name)

        if not self.name:
            errors["name"] = "Название тега не может быть пустым."

        if not self.icon:
            errors["icon"] = "Иконка тега не может быть пустой."

        if self.is_system and self.user_id is not None:
            errors["user"] = "Системный тег не должен быть привязан к пользователю."

        if not self.is_system and self.user_id is None:
            errors["user"] = "Пользовательский тег должен быть привязан к пользователю."

        if self.group_id:
            if self.group.is_system:
                pass
            elif self.user_id and self.group.user_id != self.user_id:
                errors["group"] = "Группа тега должна принадлежать тому же пользователю."
            elif self.is_system:
                errors["group"] = "Системный тег может быть связан только с системной группой."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        self.icon = self.icon.strip()
        self.color = self.color.upper()
        self.normalized_name = normalize_tag_text(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


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
    category_group = models.CharField(
        max_length=30,
        choices=BudgetCategoryGroup.choices,
        default=BudgetCategoryGroup.MAIN,
        verbose_name="Группа бюджета",
    )
    period_type = models.CharField(
        max_length=20,
        choices=BudgetPeriodType.choices,
        default=BudgetPeriodType.MONTH,
        verbose_name="Тип периода",
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
    kind = models.CharField(
        max_length=20,
        choices=BudgetKind.choices,
        default=BudgetKind.EXPENSE,
        verbose_name="Тип бюджета",
    )
    rollover = models.BooleanField(
        default=False,
        verbose_name="Перенос остатка на следующий период",
    )
    paused = models.BooleanField(
        default=False,
        verbose_name="На паузе",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
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
            models.CheckConstraint(
                condition=models.Q(period_type__in=BudgetPeriodType.values),
                name="budget_period_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=BudgetKind.values),
                name="budget_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(category_group__in=BudgetCategoryGroup.values),
                name="budget_category_group_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__regex=r"^[A-Z]{3}$"),
                name="budget_currency_code_format",
            ),
            models.UniqueConstraint(
                fields=[
                    "user",
                    "category",
                    "kind",
                    "period_type",
                    "period_start",
                    "period_end",
                ],
                name="unique_budget_kind_category_period",
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
            models.Index(fields=["user", "period_type"], name="idx_budget_user_period_type"),
            models.Index(fields=["user", "kind"], name="idx_budget_user_kind"),
            models.Index(fields=["user", "category_group"], name="idx_budget_user_group"),
            models.Index(fields=["user", "paused"], name="idx_budget_user_paused"),
            models.Index(fields=["user", "currency"], name="idx_budget_user_currency"),
            models.Index(
                fields=["user", "kind", "period_type", "period_start"],
                name="idx_budget_kind_period",
            ),
        ]

    @property
    def limit_amount(self) -> Decimal:
        return self.amount_limit

    @property
    def status(self) -> str:
        if self.paused:
            return "paused"

        if not self.is_active:
            return "inactive"

        return "active"

    def clean(self) -> None:
        errors = {}

        if self.currency:
            self.currency = self.currency.upper()

        if self.period_start and self.period_end and self.period_end < self.period_start:
            errors["period_end"] = (
                "Дата окончания периода не может быть раньше даты начала."
            )

        if self.period_type not in BudgetPeriodType.values:
            errors["period_type"] = "Недопустимый тип периода бюджета."

        if self.kind not in BudgetKind.values:
            errors["kind"] = "Недопустимый тип бюджета."

        if self.category_group not in BudgetCategoryGroup.values:
            errors["category_group"] = "Недопустимая группа бюджета."

        if self.category_id and self.user_id and self.category.user_id != self.user_id:
            errors["category"] = "Категория бюджета должна принадлежать пользователю."

        if self.category_id and self.kind and self.category.type != self.kind:
            errors["category"] = "Тип категории должен совпадать с типом бюджета."

        if self.category_id and not self.category.is_active:
            errors["category"] = "Нельзя использовать неактивную категорию в бюджете."

        if self.category_id and self.category.is_archived:
            errors["category"] = "Нельзя использовать архивную категорию в бюджете."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.currency:
            self.currency = self.currency.upper()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.category.name}: {self.amount_limit} {self.currency}"


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
    category = models.CharField(
        max_length=20,
        choices=GoalCategory.choices,
        default=GoalCategory.SAVINGS,
        verbose_name="Категория цели",
    )
    priority = models.CharField(
        max_length=20,
        choices=GoalPriority.choices,
        default=GoalPriority.MEDIUM,
        verbose_name="Приоритет",
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
    icon = models.CharField(
        max_length=50,
        default="target",
        verbose_name="Иконка",
    )
    color = models.CharField(
        max_length=7,
        default="#4F46E5",
        validators=[hex_color_validator],
        verbose_name="Цвет",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
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
            models.CheckConstraint(
                condition=models.Q(category__in=GoalCategory.values),
                name="goal_category_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(priority__in=GoalPriority.values),
                name="goal_priority_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(color__regex=r"^#[0-9A-Fa-f]{6}$"),
                name="goal_color_hex_format",
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
            models.Index(fields=["user", "category"], name="idx_goal_user_category"),
            models.Index(fields=["user", "priority"], name="idx_goal_user_priority"),
            models.Index(
                fields=["user", "status", "deadline"],
                name="idx_goal_user_status_deadline",
            ),
        ]

    @property
    def progress_percent(self) -> Decimal:
        if self.target_amount <= 0:
            return Decimal("0.00")

        percent = self.current_amount / self.target_amount * Decimal("100")
        return min(percent, Decimal("100.00")).quantize(Decimal("0.01"))

    def clean(self) -> None:
        errors = {}

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт цели должен принадлежать пользователю."

        if self.category not in GoalCategory.values:
            errors["category"] = "Недопустимая категория цели."

        if self.priority not in GoalPriority.values:
            errors["priority"] = "Недопустимый приоритет цели."

        if self.status not in GoalStatus.values:
            errors["status"] = "Недопустимый статус цели."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name}: {self.current_amount}/{self.target_amount}"


class GoalContribution(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="goal_contributions",
        verbose_name="Пользователь",
    )
    goal = models.ForeignKey(
        Goal,
        on_delete=models.PROTECT,
        related_name="contributions",
        verbose_name="Цель",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goal_contributions",
        verbose_name="Счёт-источник",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goal_contributions",
        verbose_name="Связанная операция",
    )
    account_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Название счёта на момент пополнения",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма пополнения",
    )
    contribution_date = models.DateField(
        verbose_name="Дата пополнения",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Пополнение цели"
        verbose_name_plural = "Пополнения целей"
        ordering = ["-contribution_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="goal_contribution_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_gcontrib_user"),
            models.Index(fields=["goal", "contribution_date"], name="idx_gcontrib_goal_dt"),
            models.Index(
                fields=["user", "goal", "contribution_date"],
                name="idx_gcontrib_user_goal_dt",
            ),
            models.Index(fields=["account"], name="idx_gcontrib_account"),
            models.Index(fields=["transaction"], name="idx_gcontrib_tx"),
        ]

    def clean(self) -> None:
        errors = {}

        if self.goal_id and self.user_id and self.goal.user_id != self.user_id:
            errors["goal"] = "Цель должна принадлежать пользователю пополнения."

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт пополнения должен принадлежать пользователю."

        if self.transaction_id and self.user_id and self.transaction.user_id != self.user_id:
            errors["transaction"] = "Операция должна принадлежать пользователю."

        if (
            self.transaction_id
            and self.account_id
            and self.transaction.account_id != self.account_id
        ):
            errors["transaction"] = (
                "Связанная операция должна относиться к счёту пополнения."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.account_id and not self.account_name:
            self.account_name = self.account.name

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.goal.name}: +{self.amount}"


class Notification(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Пользователь",
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Заголовок уведомления",
    )
    body = models.TextField(
        blank=True,
        verbose_name="Текст уведомления",
    )
    type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        verbose_name="Тип уведомления",
    )
    channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        verbose_name="Канал доставки",
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=NotificationDeliveryStatus.choices,
        default=NotificationDeliveryStatus.DELIVERED,
        verbose_name="Статус доставки",
    )
    delivery_error = models.TextField(
        blank=True,
        verbose_name="Ошибка доставки",
    )
    icon = models.CharField(
        max_length=50,
        default="bell",
        verbose_name="Иконка",
    )
    icon_tone = models.CharField(
        max_length=20,
        choices=NotificationIconTone.choices,
        default=NotificationIconTone.PRIMARY,
        verbose_name="Тон иконки",
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name="Прочитано",
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата прочтения",
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name="В архиве",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата архивации",
    )
    entity_kind = models.CharField(
        max_length=20,
        choices=NotificationEntityKind.choices,
        blank=True,
        verbose_name="Тип связанной сущности",
    )
    entity_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID связанной сущности",
    )
    entity_route_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Маршрут связанной сущности",
    )
    entity_label = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Название связанной сущности",
    )
    entity_tag = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Тег связанной сущности",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Сумма",
    )
    account_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Название счёта",
    )
    category_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Название категории",
    )
    related_goal_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Название связанной цели",
    )
    related_goal_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Процент связанной цели",
    )
    delivery_steps = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Шаги доставки",
    )

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(type__in=NotificationType.values),
                name="notification_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(channel__in=NotificationChannel.values),
                name="notification_channel_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(delivery_status__in=NotificationDeliveryStatus.values),
                name="notif_delivery_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(icon_tone__in=NotificationIconTone.values),
                name="notif_icon_tone_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(entity_kind="")
                    | models.Q(entity_kind__in=NotificationEntityKind.values)
                ),
                name="notif_entity_kind_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_notif_user"),
            models.Index(fields=["user", "is_read"], name="idx_notif_user_read"),
            models.Index(fields=["user", "is_archived"], name="idx_notif_user_archived"),
            models.Index(fields=["user", "type"], name="idx_notif_user_type"),
            models.Index(fields=["user", "channel"], name="idx_notif_user_channel"),
            models.Index(fields=["user", "created_at"], name="idx_notif_user_created"),
            models.Index(fields=["user", "entity_kind", "entity_id"], name="idx_notif_entity"),
            models.Index(fields=["user", "delivery_status"], name="idx_notif_delivery"),
        ]

    @property
    def status(self) -> str:
        if self.is_archived:
            return "archived"

        if self.is_read:
            return "read"

        return "unread"

    def clean(self) -> None:
        errors = {}

        if self.type not in NotificationType.values:
            errors["type"] = "Недопустимый тип уведомления."

        if self.channel not in NotificationChannel.values:
            errors["channel"] = "Недопустимый канал уведомления."

        if self.delivery_status not in NotificationDeliveryStatus.values:
            errors["delivery_status"] = "Недопустимый статус доставки."

        if self.icon_tone not in NotificationIconTone.values:
            errors["icon_tone"] = "Недопустимый тон иконки."

        if self.entity_kind and self.entity_kind not in NotificationEntityKind.values:
            errors["entity_kind"] = "Недопустимый тип связанной сущности."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

class NotificationSettings(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_settings",
        verbose_name="Пользователь",
    )
    in_app_enabled = models.BooleanField(
        default=True,
        verbose_name="In-app уведомления включены",
    )
    email_enabled = models.BooleanField(
        default=True,
        verbose_name="Email уведомления включены",
    )
    push_enabled = models.BooleanField(
        default=True,
        verbose_name="Push уведомления включены",
    )
    sms_enabled = models.BooleanField(
        default=True,
        verbose_name="SMS уведомления включены",
    )
    operation_enabled = models.BooleanField(
        default=True,
        verbose_name="Уведомления по операциям включены",
    )
    goal_enabled = models.BooleanField(
        default=True,
        verbose_name="Уведомления по целям включены",
    )
    budget_enabled = models.BooleanField(
        default=True,
        verbose_name="Уведомления по бюджетам включены",
    )
    system_enabled = models.BooleanField(
        default=True,
        verbose_name="Системные уведомления включены",
    )
    security_enabled = models.BooleanField(
        default=True,
        verbose_name="Уведомления безопасности включены",
    )
    marketing_enabled = models.BooleanField(
        default=False,
        verbose_name="Маркетинговые уведомления включены",
    )
    quiet_hours_enabled = models.BooleanField(
        default=False,
        verbose_name="Тихие часы включены",
    )
    quiet_hours_start = models.TimeField(
        default=time(22, 0),
        verbose_name="Начало тихих часов",
    )
    quiet_hours_end = models.TimeField(
        default=time(8, 0),
        verbose_name="Окончание тихих часов",
    )
    quiet_hours_days = models.JSONField(
        default=default_quiet_hours_days,
        blank=True,
        verbose_name="Дни тихих часов",
    )

    class Meta:
        verbose_name = "Настройки уведомлений"
        verbose_name_plural = "Настройки уведомлений"
        ordering = ["user_id"]

    CHANNEL_FIELD_MAP = {
        NotificationChannel.IN_APP: "in_app_enabled",
        NotificationChannel.EMAIL: "email_enabled",
        NotificationChannel.PUSH: "push_enabled",
        NotificationChannel.SMS: "sms_enabled",
    }

    TYPE_FIELD_MAP = {
        NotificationType.OPERATION: "operation_enabled",
        NotificationType.GOAL: "goal_enabled",
        NotificationType.BUDGET: "budget_enabled",
        NotificationType.SYSTEM: "system_enabled",
        NotificationType.SECURITY: "security_enabled",
        NotificationType.MARKETING: "marketing_enabled",
    }

    def is_channel_enabled(self, channel: str) -> bool:
        field_name = self.CHANNEL_FIELD_MAP.get(channel)

        if not field_name:
            return False

        return bool(getattr(self, field_name))

    def is_type_enabled(self, notification_type: str) -> bool:
        field_name = self.TYPE_FIELD_MAP.get(notification_type)

        if not field_name:
            return False

        return bool(getattr(self, field_name))

    def is_quiet_time(self, moment=None) -> bool:
        if not self.quiet_hours_enabled:
            return False

        if moment is None:
            moment = timezone.localtime()

        day_key = moment.strftime("%a").lower()[:3]

        if day_key not in self.quiet_hours_days:
            return False

        current_time = moment.time()
        start_time = self.quiet_hours_start
        end_time = self.quiet_hours_end

        if start_time <= end_time:
            return start_time <= current_time < end_time

        return current_time >= start_time or current_time < end_time

    def clean(self) -> None:
        errors = {}

        if not isinstance(self.quiet_hours_days, list):
            errors["quiet_hours_days"] = "Дни тихих часов должны быть списком."

        else:
            invalid_days = [
                day
                for day in self.quiet_hours_days
                if day not in NOTIFICATION_QUIET_HOURS_DAYS
            ]

            if invalid_days:
                errors["quiet_hours_days"] = (
                    "Недопустимые дни тихих часов: "
                    f"{', '.join(invalid_days)}."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"Настройки уведомлений пользователя {self.user_id}"


class RecurringTransaction(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recurring_transactions",
        verbose_name="Пользователь",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="recurring_transactions",
        verbose_name="Счёт",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="recurring_transactions",
        verbose_name="Категория",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Название регулярной операции",
    )
    type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.EXPENSE,
        verbose_name="Тип операции",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма",
    )
    frequency = models.CharField(
        max_length=20,
        choices=RecurringFrequency.choices,
        default=RecurringFrequency.MONTHLY,
        verbose_name="Периодичность",
    )
    day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="День месяца",
    )
    start_date = models.DateField(
        verbose_name="Дата начала",
    )
    has_end = models.BooleanField(
        default=False,
        verbose_name="Есть дата окончания",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания",
    )
    next_charge_date = models.DateField(
        verbose_name="Дата следующего списания",
    )
    last_charge_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата последнего списания",
    )
    status = models.CharField(
        max_length=20,
        choices=RecurringStatus.choices,
        default=RecurringStatus.ACTIVE,
        verbose_name="Статус",
    )
    template_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID шаблона",
    )
    template_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Название шаблона",
    )
    created_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество созданных операций",
    )
    last_error_code = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Код последней ошибки",
    )
    last_error_message = models.TextField(
        blank=True,
        verbose_name="Сообщение последней ошибки",
    )
    last_failed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата последней ошибки",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Регулярная операция"
        verbose_name_plural = "Регулярные операции"
        ordering = ["next_charge_date", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="rtx_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=TransactionType.values),
                name="rtx_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(frequency__in=RecurringFrequency.values),
                name="rtx_frequency_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RecurringStatus.values),
                name="rtx_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(day_of_month__isnull=True)
                    | (
                        models.Q(day_of_month__gte=1)
                        & models.Q(day_of_month__lte=31)
                    )
                ),
                name="rtx_day_of_month_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(has_end=False)
                    | models.Q(end_date__gte=models.F("start_date"))
                ),
                name="rtx_date_range_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_rtx_user"),
            models.Index(fields=["user", "status"], name="idx_rtx_user_status"),
            models.Index(fields=["user", "frequency"], name="idx_rtx_user_freq"),
            models.Index(fields=["user", "account"], name="idx_rtx_user_account"),
            models.Index(fields=["user", "category"], name="idx_rtx_user_category"),
            models.Index(fields=["user", "next_charge_date"], name="idx_rtx_user_next"),
            models.Index(fields=["user", "status", "next_charge_date"], name="idx_rtx_status_next"),
        ]

    def clean(self) -> None:
        errors = {}

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт должен принадлежать пользователю."

        if self.category_id and self.user_id and self.category.user_id != self.user_id:
            errors["category"] = "Категория должна принадлежать пользователю."

        if self.category_id and self.type and self.category.type != self.type:
            errors["category"] = "Тип категории должен совпадать с типом операции."

        if self.account_id and not self.account.is_active:
            errors["account"] = "Нельзя использовать неактивный счёт."

        if self.account_id and self.account.is_archived:
            errors["account"] = "Нельзя использовать архивный счёт."

        if self.category_id and not self.category.is_active:
            errors["category"] = "Нельзя использовать неактивную категорию."

        if self.category_id and self.category.is_archived:
            errors["category"] = "Нельзя использовать архивную категорию."

        if self.frequency not in RecurringFrequency.values:
            errors["frequency"] = "Недопустимая периодичность."

        if self.status not in RecurringStatus.values:
            errors["status"] = "Недопустимый статус."

        if self.type not in TransactionType.values:
            errors["type"] = "Недопустимый тип операции."

        if self.day_of_month is not None and not 1 <= self.day_of_month <= 31:
            errors["day_of_month"] = "День месяца должен быть от 1 до 31."

        if self.has_end and not self.end_date:
            errors["end_date"] = "Укажите дату окончания."

        if self.has_end and self.end_date and self.start_date and self.end_date < self.start_date:
            errors["end_date"] = "Дата окончания не может быть раньше даты начала."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name}: {self.amount}"


class RecurringTransactionCharge(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recurring_transaction_charges",
        verbose_name="Пользователь",
    )
    recurring_transaction = models.ForeignKey(
        RecurringTransaction,
        on_delete=models.CASCADE,
        related_name="charges",
        verbose_name="Регулярная операция",
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recurring_charges",
        verbose_name="Созданная операция",
    )
    charged_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Дата попытки списания",
    )
    scheduled_date = models.DateField(
        verbose_name="Плановая дата списания",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма",
    )
    status = models.CharField(
        max_length=20,
        choices=RecurringChargeStatus.choices,
        default=RecurringChargeStatus.SUCCESS,
        verbose_name="Статус списания",
    )
    error_code = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Код ошибки",
    )
    error_message = models.TextField(
        blank=True,
        verbose_name="Сообщение ошибки",
    )

    class Meta:
        verbose_name = "История регулярного списания"
        verbose_name_plural = "История регулярных списаний"
        ordering = ["-charged_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="rtx_charge_amount_pos",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RecurringChargeStatus.values),
                name="rtx_charge_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_rtx_charge_user"),
            models.Index(fields=["recurring_transaction"], name="idx_rtx_charge_rtx"),
            models.Index(fields=["user", "status"], name="idx_rtx_charge_status"),
            models.Index(fields=["user", "charged_at"], name="idx_rtx_charge_date"),
            models.Index(fields=["transaction"], name="idx_rtx_charge_tx"),
        ]

    def clean(self) -> None:
        errors = {}

        if (
            self.recurring_transaction_id
            and self.user_id
            and self.recurring_transaction.user_id != self.user_id
        ):
            errors["recurring_transaction"] = (
                "Регулярная операция должна принадлежать пользователю."
            )

        if self.transaction_id and self.user_id and self.transaction.user_id != self.user_id:
            errors["transaction"] = "Операция должна принадлежать пользователю."

        if self.status not in RecurringChargeStatus.values:
            errors["status"] = "Недопустимый статус списания."

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.recurring_transaction_id}: {self.status}"


class PlannedTransaction(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="planned_transactions",
        verbose_name="Пользователь",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="planned_transactions",
        verbose_name="Счёт",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="planned_transactions",
        verbose_name="Категория",
    )
    converted_transaction = models.OneToOneField(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_planned_transaction",
        verbose_name="Созданная операция",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Название плановой операции",
    )
    type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.EXPENSE,
        verbose_name="Тип операции",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="Сумма",
    )
    planned_date = models.DateField(
        verbose_name="Плановая дата операции",
    )
    status = models.CharField(
        max_length=20,
        choices=PlannedStatus.choices,
        default=PlannedStatus.PENDING,
        verbose_name="Статус",
    )
    include_in_forecast = models.BooleanField(
        default=True,
        verbose_name="Учитывать в прогнозе баланса",
    )
    converted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата конвертации",
    )
    last_error_code = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Код последней ошибки",
    )
    last_error_message = models.TextField(
        blank=True,
        verbose_name="Сообщение последней ошибки",
    )
    last_failed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата последней ошибки",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )

    class Meta:
        verbose_name = "Планируемая операция"
        verbose_name_plural = "Планируемые операции"
        ordering = ["planned_date", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ptx_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=TransactionType.values),
                name="ptx_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=PlannedStatus.values),
                name="ptx_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_ptx_user"),
            models.Index(fields=["user", "status"], name="idx_ptx_user_status"),
            models.Index(fields=["user", "planned_date"], name="idx_ptx_user_date"),
            models.Index(fields=["user", "account"], name="idx_ptx_user_account"),
            models.Index(fields=["user", "category"], name="idx_ptx_user_category"),
            models.Index(fields=["user", "include_in_forecast"], name="idx_ptx_user_forecast"),
            models.Index(fields=["user", "status", "planned_date"], name="idx_ptx_status_date"),
            models.Index(fields=["converted_transaction"], name="idx_ptx_converted_tx"),
        ]

    @property
    def signed_amount(self) -> Decimal:
        if self.type == TransactionType.INCOME:
            return self.amount

        return -self.amount

    @property
    def forecast_delta(self) -> Decimal:
        if not self.include_in_forecast:
            return Decimal("0.00")

        if self.status not in {
            PlannedStatus.PENDING,
            PlannedStatus.CONFIRMED,
        }:
            return Decimal("0.00")

        return self.signed_amount

    def clean(self) -> None:
        errors = {}

        if self.account_id and self.user_id and self.account.user_id != self.user_id:
            errors["account"] = "Счёт должен принадлежать пользователю."

        if self.category_id and self.user_id and self.category.user_id != self.user_id:
            errors["category"] = "Категория должна принадлежать пользователю."

        if self.category_id and self.type and self.category.type != self.type:
            errors["category"] = "Тип категории должен совпадать с типом операции."

        if self.account_id and not self.account.is_active:
            errors["account"] = "Нельзя использовать неактивный счёт."

        if self.account_id and self.account.is_archived:
            errors["account"] = "Нельзя использовать архивный счёт."

        if self.category_id and not self.category.is_active:
            errors["category"] = "Нельзя использовать неактивную категорию."

        if self.category_id and self.category.is_archived:
            errors["category"] = "Нельзя использовать архивную категорию."

        if self.type not in TransactionType.values:
            errors["type"] = "Недопустимый тип операции."

        if self.status not in PlannedStatus.values:
            errors["status"] = "Недопустимый статус плановой операции."

        if (
            self.converted_transaction_id
            and self.user_id
            and self.converted_transaction.user_id != self.user_id
        ):
            errors["converted_transaction"] = (
                "Созданная операция должна принадлежать пользователю."
            )

        if (
            self.converted_transaction_id
            and self.account_id
            and self.converted_transaction.account_id != self.account_id
        ):
            errors["converted_transaction"] = (
                "Созданная операция должна относиться к тому же счёту."
            )

        if (
            self.converted_transaction_id
            and self.category_id
            and self.converted_transaction.category_id != self.category_id
        ):
            errors["converted_transaction"] = (
                "Созданная операция должна относиться к той же категории."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.name}: {self.amount}"

