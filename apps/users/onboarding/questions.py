from __future__ import annotations

ONBOARDING_QUIZ_VERSION = "2026.06"
ONBOARDING_QUIZ_TITLE = "Стартовая настройка личных финансов"
ONBOARDING_QUIZ_DESCRIPTION = (
    "Короткая анкета помогает подготовить приложение под задачи пользователя: "
    "контроль расходов, бюджетирование, накопления и базовые рекомендации."
)

ONBOARDING_QUESTIONS = [
    {
        "id": "mainGoal",
        "stepId": "goals",
        "order": 1,
        "type": "single_choice",
        "title": "Какая основная цель использования приложения?",
        "description": "Ответ поможет определить стартовые категории, бюджеты и рекомендации.",
        "required": True,
        "options": [
            {
                "value": "expense_control",
                "label": "Контролировать расходы",
                "description": "Понять, куда уходят деньги, и сократить лишние траты.",
            },
            {
                "value": "budget_planning",
                "label": "Планировать бюджет",
                "description": "Заранее распределять доходы по основным направлениям расходов.",
            },
            {
                "value": "savings",
                "label": "Копить на цель",
                "description": "Отслеживать прогресс накоплений и регулярные пополнения.",
            },
            {
                "value": "debt_control",
                "label": "Контролировать долги и обязательства",
                "description": "Следить за обязательными платежами и снижать риск просрочек.",
            },
        ],
    },
    {
        "id": "incomeType",
        "stepId": "income",
        "order": 2,
        "type": "single_choice",
        "title": "Какой у вас основной тип дохода?",
        "description": "Используется для выбора стартового сценария планирования.",
        "required": True,
        "options": [
            {"value": "regular", "label": "Регулярный доход"},
            {"value": "irregular", "label": "Нерегулярный доход"},
            {"value": "mixed", "label": "Есть регулярный и дополнительный доход"},
            {"value": "none", "label": "Пока нет стабильного дохода"},
        ],
    },
    {
        "id": "expenseAreas",
        "stepId": "expenses",
        "order": 3,
        "type": "multi_choice",
        "title": "Какие категории расходов для вас наиболее важны?",
        "description": "По этим направлениям позже можно создать стартовые категории и бюджеты.",
        "required": True,
        "minSelected": 1,
        "maxSelected": 6,
        "options": [
            {"value": "food", "label": "Продукты и кафе"},
            {"value": "transport", "label": "Транспорт"},
            {"value": "housing", "label": "Жильё и коммунальные платежи"},
            {"value": "subscriptions", "label": "Подписки и сервисы"},
            {"value": "health", "label": "Здоровье"},
            {"value": "education", "label": "Образование"},
            {"value": "entertainment", "label": "Развлечения"},
            {"value": "travel", "label": "Путешествия"},
        ],
    },
    {
        "id": "budgetStyle",
        "stepId": "budget",
        "order": 4,
        "type": "single_choice",
        "title": "Какой стиль контроля бюджета вам ближе?",
        "description": "Поможет выбрать будущие рекомендации по лимитам и уведомлениям.",
        "required": True,
        "options": [
            {"value": "strict", "label": "Строгие лимиты"},
            {"value": "balanced", "label": "Баланс между контролем и гибкостью"},
            {"value": "flexible", "label": "Мягкий контроль без жёстких ограничений"},
        ],
    },
    {
        "id": "hasSavingsGoal",
        "stepId": "goals",
        "order": 5,
        "type": "boolean",
        "title": "Есть ли у вас финансовая цель для накоплений?",
        "description": "Например, техника, поездка, подушка безопасности или крупная покупка.",
        "required": True,
    },
    {
        "id": "defaultCurrency",
        "stepId": "settings",
        "order": 6,
        "type": "single_choice",
        "title": "Какая валюта будет основной?",
        "description": "Значение используется как предпочтение для будущей начальной настройки.",
        "required": True,
        "options": [
            {"value": "RUB", "label": "Российский рубль"},
            {"value": "USD", "label": "Доллар США"},
            {"value": "EUR", "label": "Евро"},
        ],
    },
]

ONBOARDING_STEPS = [
    {
        "id": "goals",
        "order": 1,
        "title": "Цели",
        "description": "Определяем, зачем пользователь начинает вести личные финансы.",
    },
    {
        "id": "income",
        "order": 2,
        "title": "Доходы",
        "description": "Уточняем регулярность доходов для будущей аналитики.",
    },
    {
        "id": "expenses",
        "order": 3,
        "title": "Расходы",
        "description": "Выбираем важные направления расходов.",
    },
    {
        "id": "budget",
        "order": 4,
        "title": "Бюджет",
        "description": "Настраиваем предпочтительный стиль контроля лимитов.",
    },
    {
        "id": "settings",
        "order": 5,
        "title": "Настройки",
        "description": "Фиксируем базовые предпочтения интерфейса и валюты.",
    },
]


def get_onboarding_questions() -> list[dict]:
    return [question.copy() for question in ONBOARDING_QUESTIONS]


def get_onboarding_steps() -> list[dict]:
    questions_by_step: dict[str, list[dict]] = {}

    for question in get_onboarding_questions():
        questions_by_step.setdefault(question["stepId"], []).append(question)

    steps = []
    for step in ONBOARDING_STEPS:
        step_payload = step.copy()
        step_payload["questions"] = sorted(
            questions_by_step.get(step["id"], []),
            key=lambda item: item["order"],
        )
        steps.append(step_payload)

    return steps


def get_onboarding_quiz_config() -> dict:
    questions = get_onboarding_questions()

    return {
        "version": ONBOARDING_QUIZ_VERSION,
        "title": ONBOARDING_QUIZ_TITLE,
        "description": ONBOARDING_QUIZ_DESCRIPTION,
        "estimatedMinutes": 2,
        "totalQuestions": len(questions),
        "steps": get_onboarding_steps(),
    }


def get_question_map() -> dict[str, dict]:
    return {question["id"]: question for question in ONBOARDING_QUESTIONS}
