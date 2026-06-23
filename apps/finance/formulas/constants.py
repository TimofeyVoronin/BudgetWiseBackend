from __future__ import annotations

FORMULA_ID_DEFAULT = "draft-default"
FORMULA_IDE_TAG = "finance-formula-ide"
MAX_FORMULA_CODE_LENGTH = 10000
MAX_CONSTRUCTOR_BLOCKS = 200

DEFAULT_FORMULA_CODE = """// Пример формулы: прогноз остатка на конец периода
LET start_balance = BALANCE(
    account: "Основной счёт",
    date: START_OF($period)
);

LET income = SUM(
    TRANSACTIONS(
        account: "Основной счёт",
        type: INCOME,
        date: $period
    )
);

LET expenses = SUM(
    TRANSACTIONS(
        account: "Основной счёт",
        type: EXPENSE,
        date: $period
    )
);

RETURN start_balance + income - expenses;"""

DEFAULT_CONSTRUCTOR_BLOCKS = [
    {"id": "b1", "kind": "function", "label": "SUM"},
    {"id": "b2", "kind": "variable", "label": "transactions.amount"},
    {"id": "b3", "kind": "function", "label": "WHERE"},
    {"id": "b4", "kind": "condition", "label": "category = \"Продукты\""},
]

FORMULA_IDE_META = {
    "variable_groups": [
        {
            "id": "period",
            "title": "Период",
            "chip_class": "period",
            "items": ["$period", "$start_date", "$end_date", "$month", "$year"],
        },
        {
            "id": "accounts",
            "title": "Счета",
            "chip_class": "period",
            "items": ["$account", "$accounts", "$currency"],
        },
        {
            "id": "functions",
            "title": "Функции",
            "chip_class": "function",
            "items": ["BALANCE()", "TRANSACTIONS()", "SUM()", "AVG()"],
        },
        {
            "id": "operators",
            "title": "Операторы",
            "chip_class": "operator",
            "items": ["+", "-", "*", "/", "==", "!=", ">", "<", "&&", "||"],
        },
        {
            "id": "constants",
            "title": "Константы",
            "chip_class": "constant",
            "items": ["INCOME", "EXPENSE", "TRANSFER", "TODAY()"],
        },
    ],
    "constructor_variables": [
        {"id": "income", "title": "Доходы", "icon": "mdi-cash-plus"},
        {"id": "expense", "title": "Расходы", "icon": "mdi-cash-minus"},
        {"id": "balance", "title": "Баланс счёта", "icon": "mdi-bank-outline"},
        {"id": "budget-limit", "title": "Лимит бюджета", "icon": "mdi-chart-donut"},
    ],
    "constructor_operators": [
        {"id": "plus", "label": "+"},
        {"id": "minus", "label": "-"},
        {"id": "mul", "label": "*"},
        {"id": "div", "label": "/"},
        {"id": "sum", "label": "SUM"},
        {"id": "avg", "label": "AVG"},
        {"id": "if", "label": "IF"},
    ],
    "autocomplete_items": [
        {"id": "sum", "name": "SUM()", "description": "Сумма всех значений"},
        {"id": "avg", "name": "AVG()", "description": "Среднее значение"},
        {"id": "min", "name": "MIN()", "description": "Минимальное значение"},
        {"id": "max", "name": "MAX()", "description": "Максимальное значение"},
        {"id": "count", "name": "COUNT()", "description": "Количество значений"},
        {"id": "if", "name": "IF()", "description": "Условное выражение"},
        {"id": "round", "name": "ROUND()", "description": "Округление числа"},
    ],
}
