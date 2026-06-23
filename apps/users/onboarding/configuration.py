from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finance.currencies.services import (
    ensure_user_currencies,
    get_user_currency_by_code,
    normalize_currency_code,
)
from apps.finance.models import (
    Budget,
    BudgetCategoryGroup,
    BudgetKind,
    BudgetPeriodType,
    Category,
    Goal,
    GoalCategory,
    GoalPriority,
    TransactionType,
)
from apps.users.app_settings.services import get_or_create_user_app_settings


DEFAULT_ONBOARDING_RESULT = {
    "configurationApplied": False,
    "nextStep": "initial_configuration",
    "created": {
        "categories": 0,
        "goals": 0,
        "budgets": 0,
        "recommendations": 0,
    },
    "createdIds": {
        "categories": [],
        "goals": [],
        "budgets": [],
    },
    "appliedSettings": {},
    "recommendations": [],
}

EXPENSE_AREA_CONFIGURATION = {
    "food": {
        "name": "Продукты и кафе",
        "icon": "utensils",
        "color": "#10B981",
        "budgetLimit": Decimal("25000.00"),
    },
    "transport": {
        "name": "Транспорт",
        "icon": "bus",
        "color": "#3B82F6",
        "budgetLimit": Decimal("7000.00"),
    },
    "housing": {
        "name": "Жильё и коммунальные платежи",
        "icon": "home",
        "color": "#8B5CF6",
        "budgetLimit": Decimal("30000.00"),
    },
    "subscriptions": {
        "name": "Подписки и сервисы",
        "icon": "repeat",
        "color": "#F59E0B",
        "budgetLimit": Decimal("3000.00"),
    },
    "health": {
        "name": "Здоровье",
        "icon": "heart-pulse",
        "color": "#EF4444",
        "budgetLimit": Decimal("8000.00"),
    },
    "education": {
        "name": "Образование",
        "icon": "graduation-cap",
        "color": "#6366F1",
        "budgetLimit": Decimal("10000.00"),
    },
    "entertainment": {
        "name": "Развлечения",
        "icon": "gamepad-2",
        "color": "#EC4899",
        "budgetLimit": Decimal("8000.00"),
    },
    "travel": {
        "name": "Путешествия",
        "icon": "plane",
        "color": "#06B6D4",
        "budgetLimit": Decimal("15000.00"),
    },
}

INCOME_CATEGORY_CONFIGURATION = {
    "regular": [
        {
            "name": "Зарплата",
            "icon": "briefcase",
            "color": "#22C55E",
        },
    ],
    "irregular": [
        {
            "name": "Проектный доход",
            "icon": "wallet-cards",
            "color": "#14B8A6",
        },
    ],
    "mixed": [
        {
            "name": "Зарплата",
            "icon": "briefcase",
            "color": "#22C55E",
        },
        {
            "name": "Дополнительный доход",
            "icon": "plus-circle",
            "color": "#84CC16",
        },
    ],
    "none": [
        {
            "name": "Прочие доходы",
            "icon": "coins",
            "color": "#64748B",
        },
    ],
}

BUDGET_STYLE_MULTIPLIERS = {
    "strict": Decimal("0.85"),
    "balanced": Decimal("1.00"),
    "flexible": Decimal("1.20"),
}

SAVINGS_GOAL_NAME = "Финансовая подушка"
SAVINGS_GOAL_TARGET_AMOUNT = Decimal("100000.00")


def build_default_onboarding_result() -> dict:
    return deepcopy(DEFAULT_ONBOARDING_RESULT)


@transaction.atomic
def apply_onboarding_initial_configuration(user, answers: dict, previous_result: dict | None = None) -> dict:
    """Apply onboarding answers to initial user configuration once.

    The function is intentionally idempotent. If the survey already has a
    successful configuration result, the existing result is returned and no
    additional finance objects are created.
    """
    if isinstance(previous_result, dict) and previous_result.get("configurationApplied") is True:
        return previous_result

    result = build_default_onboarding_result()
    created_category_ids = _create_starter_categories(user, answers)
    created_goal_ids = _create_starter_goals(user, answers)
    created_budget_ids = _create_starter_budgets(user, answers)
    applied_settings = _apply_default_settings(user, answers)
    recommendations = _build_onboarding_recommendations(answers)

    result["configurationApplied"] = True
    result["nextStep"] = "dashboard"
    result["created"] = {
        "categories": len(created_category_ids),
        "goals": len(created_goal_ids),
        "budgets": len(created_budget_ids),
        "recommendations": len(recommendations),
    }
    result["createdIds"] = {
        "categories": created_category_ids,
        "goals": created_goal_ids,
        "budgets": created_budget_ids,
    }
    result["appliedSettings"] = applied_settings
    result["recommendations"] = recommendations

    return result


def _create_starter_categories(user, answers: dict) -> list[int]:
    created_ids: list[int] = []
    sort_order = 10

    for area in answers.get("expenseAreas") or []:
        config = EXPENSE_AREA_CONFIGURATION.get(area)
        if not config:
            continue

        category, created = Category.objects.get_or_create(
            user=user,
            name=config["name"],
            type=TransactionType.EXPENSE,
            defaults={
                "icon": config["icon"],
                "color": config["color"],
                "sort_order": sort_order,
                "is_favorite": True,
                "is_active": True,
                "is_archived": False,
            },
        )
        if created:
            created_ids.append(category.pk)
        sort_order += 10

    income_type = answers.get("incomeType")
    income_categories = INCOME_CATEGORY_CONFIGURATION.get(income_type, [])

    for config in income_categories:
        category, created = Category.objects.get_or_create(
            user=user,
            name=config["name"],
            type=TransactionType.INCOME,
            defaults={
                "icon": config["icon"],
                "color": config["color"],
                "sort_order": sort_order,
                "is_favorite": True,
                "is_active": True,
                "is_archived": False,
            },
        )
        if created:
            created_ids.append(category.pk)
        sort_order += 10

    return created_ids


def _create_starter_goals(user, answers: dict) -> list[int]:
    should_create_savings_goal = bool(answers.get("hasSavingsGoal")) or answers.get("mainGoal") == "savings"
    if not should_create_savings_goal:
        return []

    goal, created = Goal.objects.get_or_create(
        user=user,
        name=SAVINGS_GOAL_NAME,
        defaults={
            "category": GoalCategory.SAVINGS,
            "priority": GoalPriority.HIGH if answers.get("mainGoal") == "savings" else GoalPriority.MEDIUM,
            "target_amount": SAVINGS_GOAL_TARGET_AMOUNT,
            "current_amount": Decimal("0.00"),
            "deadline": timezone.localdate() + timedelta(days=180),
            "icon": "shield-check",
            "color": "#4F46E5",
            "comment": "Создано автоматически после onboarding-анкеты.",
        },
    )

    return [goal.pk] if created else []


def _create_starter_budgets(user, answers: dict) -> list[int]:
    created_ids: list[int] = []
    currency = normalize_currency_code(answers.get("defaultCurrency")) or "RUB"
    period_start, period_end = _current_month_period()
    multiplier = BUDGET_STYLE_MULTIPLIERS.get(answers.get("budgetStyle"), Decimal("1.00"))

    for area in answers.get("expenseAreas") or []:
        config = EXPENSE_AREA_CONFIGURATION.get(area)
        if not config:
            continue

        category = Category.objects.filter(
            user=user,
            name=config["name"],
            type=TransactionType.EXPENSE,
            is_active=True,
            is_archived=False,
        ).first()
        if category is None:
            continue

        amount_limit = (config["budgetLimit"] * multiplier).quantize(Decimal("0.01"))
        budget, created = Budget.objects.get_or_create(
            user=user,
            category=category,
            kind=BudgetKind.EXPENSE,
            period_type=BudgetPeriodType.MONTH,
            period_start=period_start,
            period_end=period_end,
            defaults={
                "category_group": BudgetCategoryGroup.MAIN,
                "amount_limit": amount_limit,
                "currency": currency,
                "rollover": False,
                "paused": False,
                "is_active": True,
                "comment": "Создано автоматически после onboarding-анкеты.",
            },
        )
        if created:
            created_ids.append(budget.pk)

    return created_ids


def _apply_default_settings(user, answers: dict) -> dict:
    currency = normalize_currency_code(answers.get("defaultCurrency"))
    if not currency:
        return {}

    ensure_user_currencies(user)
    user_currency = get_user_currency_by_code(user, currency)
    if user_currency is None:
        return {}

    if not user_currency.is_visible:
        user_currency.is_visible = True
        user_currency.save(update_fields=["is_visible", "updated_at"])

    settings = get_or_create_user_app_settings(user)
    changed = settings.default_currency != currency

    if changed:
        settings.default_currency = currency
        settings.save(update_fields=["default_currency", "updated_at"])

    return {
        "defaultCurrency": currency,
        "defaultCurrencyChanged": changed,
    }


def _build_onboarding_recommendations(answers: dict) -> list[dict]:
    recommendations = []
    main_goal = answers.get("mainGoal")
    income_type = answers.get("incomeType")
    budget_style = answers.get("budgetStyle")

    if main_goal == "expense_control":
        recommendations.append(
            {
                "id": "review-top-expenses",
                "title": "Проверьте крупные расходы за месяц",
                "description": "Начните с регулярного просмотра категорий, где расходы растут быстрее всего.",
            }
        )
    elif main_goal == "budget_planning":
        recommendations.append(
            {
                "id": "set-monthly-limits",
                "title": "Используйте месячные лимиты",
                "description": "Стартовые бюджеты уже подготовлены по выбранным направлениям расходов.",
            }
        )
    elif main_goal == "savings":
        recommendations.append(
            {
                "id": "top-up-savings-goal",
                "title": "Пополняйте цель регулярно",
                "description": "Даже небольшие регулярные пополнения помогают быстрее достичь цели.",
            }
        )
    elif main_goal == "debt_control":
        recommendations.append(
            {
                "id": "track-obligations",
                "title": "Отмечайте обязательные платежи",
                "description": "Добавьте регулярные операции для кредитов, рассрочек и других обязательств.",
            }
        )

    if income_type in {"irregular", "mixed"}:
        recommendations.append(
            {
                "id": "keep-reserve",
                "title": "Сформируйте резерв на нерегулярные месяцы",
                "description": "При нестабильном доходе полезно держать запас на обязательные расходы.",
            }
        )

    if budget_style == "strict":
        recommendations.append(
            {
                "id": "enable-budget-alerts",
                "title": "Включите уведомления по бюджетам",
                "description": "Предупреждения помогут вовремя заметить приближение к лимиту.",
            }
        )
    elif budget_style == "flexible":
        recommendations.append(
            {
                "id": "review-weekly",
                "title": "Проверяйте бюджет раз в неделю",
                "description": "Мягкий контроль лучше работает при регулярном коротком просмотре расходов.",
            }
        )

    if not answers.get("hasSavingsGoal"):
        recommendations.append(
            {
                "id": "create-first-goal-later",
                "title": "Добавьте финансовую цель позже",
                "description": "Когда появится конкретная цель, её можно создать в разделе целей.",
            }
        )

    return recommendations


def _current_month_period() -> tuple:
    today = timezone.localdate()
    period_start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    period_end = today.replace(day=last_day)
    return period_start, period_end
