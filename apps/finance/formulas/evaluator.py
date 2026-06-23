from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.conversion import get_currency_conversion_service
from apps.finance.currencies.money import quantize_money
from apps.finance.formulas.ast_nodes import (
    AstNode,
    BinaryExpression,
    ConstantExpression,
    FormulaProgram,
    FunctionCallExpression,
    LetStatement,
    LiteralExpression,
    NamedArgument,
    NumberExpression,
    ReturnStatement,
    StringExpression,
    UnaryExpression,
    VariableExpression,
)
from apps.finance.formulas.diagnostics import FormulaDiagnostic, MAX_DIAGNOSTICS
from apps.finance.formulas.parser import parse_formula_code
from apps.finance.formulas.security import RUNTIME_ALLOWED_FUNCTIONS, validate_program_security
from apps.finance.models import Account, Transaction, TransactionType
from apps.users.app_settings.formatting import (
    format_app_money,
    get_user_app_formatting_context,
    get_user_app_today,
)

FORMULA_PREVIEW_MONTHS = 6
FORMULA_PREVIEW_ERROR_DETAIL = "В формуле найдены ошибки"


@dataclass(frozen=True)
class FormulaPreviewPeriod:
    start_date: date
    end_date: date

    @property
    def month_key(self) -> str:
        return f"{self.start_date.year:04d}-{self.start_date.month:02d}"


@dataclass(frozen=True)
class FormulaPreviewContext:
    user: object
    period: FormulaPreviewPeriod
    display_currency: str
    formatting_context: object
    converter: object


class FormulaEvaluationError(Exception):
    def __init__(self, diagnostics: Sequence[FormulaDiagnostic]) -> None:
        super().__init__(FORMULA_PREVIEW_ERROR_DETAIL)
        self.diagnostics = list(diagnostics)


class FormulaEvaluator:
    """Safe evaluator for the supported subset of the financial formula DSL.

    The evaluator never executes Python code. It walks the AST produced by the
    DSL parser and only resolves whitelisted nodes and functions.
    """

    def __init__(self, *, context: FormulaPreviewContext) -> None:
        self.context = context
        self.diagnostics: list[FormulaDiagnostic] = []
        self.variables: dict[str, Any] = {}

    def evaluate_program(self, program: FormulaProgram) -> Decimal:
        for statement in program.statements:
            if isinstance(statement, LetStatement):
                self.variables[statement.name] = self.evaluate(statement.expression)

        if program.return_statement is None:
            self.add_error(
                id="missing-return",
                line=1,
                message="В формуле должен быть оператор RETURN.",
            )
            return Decimal("0.00")

        result = self.evaluate(program.return_statement.expression)
        return self.to_decimal(result, line=program.return_statement.line)

    def evaluate(self, node: AstNode) -> Any:
        if isinstance(node, NumberExpression):
            return node.value
        if isinstance(node, StringExpression):
            return node.value
        if isinstance(node, LiteralExpression):
            return node.value
        if isinstance(node, ConstantExpression):
            return self.evaluate_constant(node)
        if isinstance(node, VariableExpression):
            return self.evaluate_variable(node)
        if isinstance(node, UnaryExpression):
            return self.evaluate_unary(node)
        if isinstance(node, BinaryExpression):
            return self.evaluate_binary(node)
        if isinstance(node, FunctionCallExpression):
            return self.evaluate_function_call(node)
        if isinstance(node, NamedArgument):
            return self.evaluate(node.expression)

        self.add_error(
            id="unsupported-node",
            line=getattr(node, "line", 1),
            message="Неподдерживаемая конструкция формулы.",
        )
        return Decimal("0.00")

    def evaluate_constant(self, node: ConstantExpression) -> str:
        constants = {
            "INCOME": TransactionType.INCOME,
            "EXPENSE": TransactionType.EXPENSE,
            "TRANSFER": "transfer",
        }
        return str(constants.get(node.name, node.name.lower()))

    def evaluate_variable(self, node: VariableExpression) -> Any:
        if node.name in self.variables:
            return self.variables[node.name]

        system_variables = {
            "$period": self.context.period,
            "$start_date": self.context.period.start_date,
            "$end_date": self.context.period.end_date,
            "$month": self.context.period.start_date.month,
            "$year": self.context.period.start_date.year,
            "$currency": self.context.display_currency,
            "$account": None,
            "$accounts": list(
                Account.objects.filter(user=self.context.user, is_archived=False).values_list("name", flat=True)
            ),
        }
        if node.name in system_variables:
            return system_variables[node.name]

        self.add_error(
            id="unknown-variable",
            line=node.line,
            message=f"Неизвестная переменная {node.name}.",
        )
        return Decimal("0.00")

    def evaluate_unary(self, node: UnaryExpression) -> Decimal:
        value = self.to_decimal(self.evaluate(node.operand), line=node.line)
        if node.operator == "-":
            return -value
        return value

    def evaluate_binary(self, node: BinaryExpression) -> Any:
        if node.operator == "&&":
            return bool(self.evaluate(node.left)) and bool(self.evaluate(node.right))
        if node.operator == "||":
            return bool(self.evaluate(node.left)) or bool(self.evaluate(node.right))

        left_raw = self.evaluate(node.left)
        right_raw = self.evaluate(node.right)

        if node.operator in {"==", "!=", ">", "<", ">=", "<="}:
            return self.compare_values(left_raw, right_raw, operator=node.operator, line=node.line)

        left = self.to_decimal(left_raw, line=node.line)
        right = self.to_decimal(right_raw, line=node.line)

        if node.operator == "+":
            return left + right
        if node.operator == "-":
            return left - right
        if node.operator == "*":
            return left * right
        if node.operator == "/":
            if right == 0:
                self.add_error(
                    id="division-by-zero",
                    line=node.line,
                    message="Деление на ноль в формуле.",
                )
                return Decimal("0.00")
            return left / right

        self.add_error(
            id="unsupported-operator",
            line=node.line,
            message=f"Оператор {node.operator} не поддерживается.",
        )
        return Decimal("0.00")

    def compare_values(self, left: Any, right: Any, *, operator: str, line: int) -> bool:
        if isinstance(left, (Decimal, int, float)) or isinstance(right, (Decimal, int, float)):
            left = self.to_decimal(left, line=line)
            right = self.to_decimal(right, line=line)

        try:
            if operator == "==":
                return left == right
            if operator == "!=":
                return left != right
            if operator == ">":
                return left > right
            if operator == "<":
                return left < right
            if operator == ">=":
                return left >= right
            if operator == "<=":
                return left <= right
        except TypeError:
            self.add_error(
                id="invalid-comparison",
                line=line,
                message="Нельзя сравнить значения разных типов в формуле.",
            )
            return False
        return False

    def evaluate_function_call(self, node: FunctionCallExpression) -> Any:
        function_name = node.name.upper()
        if function_name not in RUNTIME_ALLOWED_FUNCTIONS:
            self.add_error(
                id="unsupported-function",
                line=node.line,
                message=f"Функция {node.name} не разрешена для безопасного выполнения.",
            )
            return Decimal("0.00")

        # IF is evaluated lazily so that the unused branch does not trigger
        # execution errors such as division by zero.
        if function_name == "IF":
            return self.evaluate_if_function(node)

        positional, named = self.resolve_arguments(node.arguments)

        if function_name == "TRANSACTIONS":
            self.validate_positional_arguments(function_name=function_name, positional=positional, line=node.line)
            self.validate_named_arguments(
                function_name=function_name,
                named=named,
                allowed={"account", "type", "date"},
                line=node.line,
            )
            return self.function_transactions(named=node_named_to_mapping(named), line=node.line)
        if function_name == "BALANCE":
            self.validate_positional_arguments(function_name=function_name, positional=positional, line=node.line)
            self.validate_named_arguments(
                function_name=function_name,
                named=named,
                allowed={"account", "date"},
                line=node.line,
            )
            return self.function_balance(named=node_named_to_mapping(named), line=node.line)
        if function_name == "SUM":
            return sum_decimal_values(positional)
        if function_name == "AVG":
            values = flatten_decimal_values(positional)
            if not values:
                return Decimal("0.00")
            return sum(values, Decimal("0.00")) / Decimal(len(values))
        if function_name == "COUNT":
            values = flatten_values(positional)
            return Decimal(len(values))
        if function_name == "MIN":
            values = flatten_decimal_values(positional)
            return min(values) if values else Decimal("0.00")
        if function_name == "MAX":
            values = flatten_decimal_values(positional)
            return max(values) if values else Decimal("0.00")
        if function_name == "ROUND":
            if not positional:
                self.add_error(
                    id="invalid-function-arguments",
                    line=node.line,
                    message="Функция ROUND ожидает минимум один аргумент.",
                )
                return Decimal("0.00")
            value = self.to_decimal(positional[0], line=node.line)
            places = int(self.to_decimal(positional[1], line=node.line)) if len(positional) > 1 else 0
            if places < 0 or places > 6:
                self.add_error(
                    id="invalid-function-arguments",
                    line=node.line,
                    message="Второй аргумент ROUND должен быть числом от 0 до 6.",
                )
                places = min(max(places, 0), 6)
            quant = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
            try:
                return value.quantize(quant, rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError):
                self.add_error(
                    id="invalid-rounding",
                    line=node.line,
                    message="Не удалось округлить значение в функции ROUND.",
                )
                return Decimal("0.00")
        if function_name == "TODAY":
            if positional or named:
                self.add_error(
                    id="invalid-function-arguments",
                    line=node.line,
                    message="Функция TODAY не принимает аргументы.",
                )
            return get_user_app_today(self.context.user)
        if function_name == "START_OF":
            if len(positional) > 1:
                self.add_error(
                    id="invalid-function-arguments",
                    line=node.line,
                    message="Функция START_OF принимает не более одного аргумента.",
                )
            return self.resolve_period_start(positional[0] if positional else self.context.period, line=node.line)
        if function_name == "END_OF":
            if len(positional) > 1:
                self.add_error(
                    id="invalid-function-arguments",
                    line=node.line,
                    message="Функция END_OF принимает не более одного аргумента.",
                )
            return self.resolve_period_end(positional[0] if positional else self.context.period, line=node.line)

        self.add_error(
            id="unsupported-function",
            line=node.line,
            message=f"Функция {node.name} пока не поддерживается при предпросмотре.",
        )
        return Decimal("0.00")

    def evaluate_if_function(self, node: FunctionCallExpression) -> Any:
        if len(node.arguments) < 3:
            self.add_error(
                id="invalid-function-arguments",
                line=node.line,
                message="Функция IF ожидает три аргумента: условие, значение если истина, значение если ложь.",
            )
            return Decimal("0.00")
        if len(node.arguments) > 3:
            self.add_error(
                id="invalid-function-arguments",
                line=node.line,
                message="Функция IF принимает только три аргумента.",
            )
        condition = self.evaluate(node.arguments[0])
        branch = node.arguments[1] if bool(condition) else node.arguments[2]
        return self.evaluate(branch)

    def validate_positional_arguments(self, *, function_name: str, positional: Sequence[Any], line: int) -> None:
        if positional:
            self.add_error(
                id="invalid-function-arguments",
                line=line,
                message=f"Функция {function_name} принимает только именованные аргументы.",
            )

    def validate_named_arguments(self, *, function_name: str, named: Mapping[str, Any], allowed: set[str], line: int) -> None:
        for name in named:
            if name not in allowed:
                self.add_error(
                    id="unknown-argument",
                    line=line,
                    message=f"Аргумент {name} не поддерживается функцией {function_name}.",
                )

    def resolve_arguments(self, arguments: Sequence[AstNode]) -> tuple[list[Any], dict[str, Any]]:
        positional: list[Any] = []
        named: dict[str, Any] = {}
        for argument in arguments:
            if isinstance(argument, NamedArgument):
                named[argument.name] = self.evaluate(argument.expression)
            else:
                positional.append(self.evaluate(argument))
        return positional, named

    def function_transactions(self, *, named: Mapping[str, Any], line: int) -> list[Decimal]:
        raw_type = named.get("type")
        transaction_type = normalize_transaction_type(raw_type)
        if raw_type not in (None, "") and transaction_type is None:
            self.add_error(
                id="invalid-transaction-type",
                line=line,
                message="Тип операции должен быть INCOME или EXPENSE.",
            )
        account_name = str(named.get("account") or "").strip()
        period = self.resolve_period_from_value(named.get("date"), line=line)

        queryset = (
            Transaction.objects
            .filter(user=self.context.user, operation_date__gte=period.start_date, operation_date__lte=period.end_date)
            .select_related("account")
        )
        if transaction_type:
            queryset = queryset.filter(type=transaction_type)
        if account_name:
            queryset = queryset.filter(account__name=account_name)

        amounts: list[Decimal] = []
        for transaction in queryset:
            amounts.append(
                self.context.converter.convert_to_display(
                    transaction.amount,
                    source_currency=getattr(transaction.account, "currency", None),
                ).amount
            )
        return amounts

    def function_balance(self, *, named: Mapping[str, Any], line: int) -> Decimal:
        account_name = str(named.get("account") or "").strip()
        queryset = Account.objects.filter(user=self.context.user, is_archived=False)
        if account_name:
            queryset = queryset.filter(name=account_name)

        total = Decimal("0.00")
        for account in queryset:
            total += self.context.converter.convert_to_display(
                account.balance,
                source_currency=account.currency,
            ).amount
        return total

    def resolve_period_from_value(self, value: Any, *, line: int) -> FormulaPreviewPeriod:
        if value is None:
            return self.context.period
        if isinstance(value, FormulaPreviewPeriod):
            return value
        if isinstance(value, date):
            return FormulaPreviewPeriod(
                start_date=date(value.year, value.month, 1),
                end_date=date(value.year, value.month, calendar.monthrange(value.year, value.month)[1]),
            )
        self.add_error(
            id="invalid-period-argument",
            line=line,
            message="Аргумент date должен быть периодом или датой.",
        )
        return self.context.period

    def resolve_period_start(self, value: Any, *, line: int) -> date:
        period = self.resolve_period_from_value(value, line=line)
        return period.start_date

    def resolve_period_end(self, value: Any, *, line: int) -> date:
        period = self.resolve_period_from_value(value, line=line)
        return period.end_date

    def to_decimal(self, value: Any, *, line: int) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool):
            return Decimal("1.00") if value else Decimal("0.00")
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, list):
            return sum_decimal_values(value)
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            self.add_error(
                id="invalid-value-type",
                line=line,
                message="Значение нельзя использовать как число в формуле.",
            )
            return Decimal("0.00")

    def add_error(self, *, id: str, line: int, message: str, severity: str = "error") -> None:
        if len(self.diagnostics) >= MAX_DIAGNOSTICS:
            return
        diagnostic = FormulaDiagnostic(id=id, line=line, message=message, severity=severity)
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)


@dataclass(frozen=True)
class FormulaPreviewResult:
    rows: list[dict[str, Any]]
    chart_points: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "chart_points": self.chart_points,
        }


def build_formula_preview(*, user, code: str, constructor_blocks: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    program, validation_result = parse_formula_code(code)
    if not validation_result.is_valid:
        raise FormulaEvaluationError([FormulaDiagnostic(**error) for error in validation_result.errors])

    security_diagnostics = validate_program_security(program)
    if security_diagnostics:
        raise FormulaEvaluationError(security_diagnostics)

    context = build_preview_context(user=user)
    evaluator = FormulaEvaluator(context=context)
    formula_result = evaluator.evaluate_program(program)
    if evaluator.diagnostics:
        raise FormulaEvaluationError(evaluator.diagnostics)

    totals = calculate_current_period_totals(context=context)
    chart_points = build_preview_chart_points(context=context)
    rows = build_preview_rows(
        user=user,
        context=context,
        income=totals[TransactionType.INCOME],
        expense=totals[TransactionType.EXPENSE],
        result=quantize_money(formula_result),
    )
    return FormulaPreviewResult(rows=rows, chart_points=chart_points).to_dict()


def build_preview_context(*, user) -> FormulaPreviewContext:
    today = get_user_app_today(user)
    start_date = date(today.year, today.month, 1)
    end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    formatting_context = get_user_app_formatting_context(user)
    converter = get_currency_conversion_service(
        user=user,
        display_currency=formatting_context.default_currency,
        require_visible_display_currency=False,
        refresh_rates=False,
    )
    return FormulaPreviewContext(
        user=user,
        period=FormulaPreviewPeriod(start_date=start_date, end_date=end_date),
        display_currency=converter.display_currency,
        formatting_context=formatting_context,
        converter=converter,
    )


def calculate_current_period_totals(*, context: FormulaPreviewContext) -> dict[str, Decimal]:
    return calculate_monthly_totals(
        context=context,
        start_date=context.period.start_date,
        end_date=context.period.end_date,
    ).get(context.period.month_key, build_empty_type_totals())


def build_preview_chart_points(*, context: FormulaPreviewContext) -> list[dict[str, Any]]:
    first_month = add_months(context.period.start_date, -(FORMULA_PREVIEW_MONTHS - 1))
    monthly_totals = calculate_monthly_totals(
        context=context,
        start_date=first_month,
        end_date=context.period.end_date,
    )

    points = []
    current = first_month
    for _ in range(FORMULA_PREVIEW_MONTHS):
        month_key = f"{current.year:04d}-{current.month:02d}"
        totals = monthly_totals.get(month_key, build_empty_type_totals())
        net = totals[TransactionType.INCOME] - totals[TransactionType.EXPENSE]
        points.append({"month": SHORT_MONTH_LABELS[current.month], "value": decimal_to_api_number(quantize_money(net))})
        current = add_months(current, 1)
    return points


def calculate_monthly_totals(*, context: FormulaPreviewContext, start_date: date, end_date: date) -> dict[str, dict[str, Decimal]]:
    month_keys = build_month_keys(start_date, end_date)
    totals = {month_key: build_empty_type_totals() for month_key in month_keys}

    rows = (
        Transaction.objects
        .filter(user=context.user, operation_date__gte=start_date, operation_date__lte=end_date)
        .annotate(month=TruncMonth("operation_date"))
        .values("month", "type", "account__currency")
        .annotate(total_amount=Sum("amount"))
        .order_by()
    )
    for row in rows:
        month_value = row["month"]
        month_date = month_value.date() if hasattr(month_value, "date") else month_value
        month_key = f"{month_date.year:04d}-{month_date.month:02d}"
        transaction_type = row["type"]
        if month_key not in totals or transaction_type not in totals[month_key]:
            continue
        converted = context.converter.convert_to_display(
            row["total_amount"] or Decimal("0.00"),
            source_currency=row["account__currency"],
        ).amount
        totals[month_key][transaction_type] += converted
    return totals


def build_preview_rows(
    *,
    user,
    context: FormulaPreviewContext,
    income: Decimal,
    expense: Decimal,
    result: Decimal,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "income",
            "label": "Итого доход",
            "value": format_preview_money(user=user, context=context, value=income),
            "highlight": False,
        },
        {
            "id": "expense",
            "label": "Итого расход",
            "value": format_preview_money(user=user, context=context, value=expense),
            "highlight": False,
        },
        {
            "id": "net",
            "label": "Чистый поток",
            "value": format_preview_money(user=user, context=context, value=result),
            "highlight": True,
        },
    ]


def format_preview_money(*, user, context: FormulaPreviewContext, value: Decimal) -> str:
    value = quantize_money(value)
    decimal_places = 0 if value == value.quantize(Decimal("1")) else 2
    return format_app_money(
        value,
        context.formatting_context,
        user=user,
        currency_code=context.display_currency,
        decimal_places=decimal_places,
    ) or f"{value} {context.display_currency}"


def build_formula_validation_failed_payload(errors: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "detail": FORMULA_PREVIEW_ERROR_DETAIL,
        "errors": list(errors),
        "error": {
            "code": "FORMULA_VALIDATION_FAILED",
            "message": FORMULA_PREVIEW_ERROR_DETAIL,
            "errors": list(errors),
        },
    }


def build_empty_type_totals() -> dict[str, Decimal]:
    return {
        TransactionType.INCOME: Decimal("0.00"),
        TransactionType.EXPENSE: Decimal("0.00"),
    }


def build_month_keys(start_date: date, end_date: date) -> list[str]:
    current = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    result = []
    while current <= last:
        result.append(f"{current.year:04d}-{current.month:02d}")
        current = add_months(current, 1)
    return result


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def normalize_transaction_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in TransactionType.values:
        return normalized
    return None


def node_named_to_mapping(named: Mapping[str, Any]) -> Mapping[str, Any]:
    return named


def flatten_values(values: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if isinstance(value, list):
            result.extend(value)
        else:
            result.append(value)
    return result


def flatten_decimal_values(values: Sequence[Any]) -> list[Decimal]:
    result: list[Decimal] = []
    for value in flatten_values(values):
        try:
            result.append(Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return result


def sum_decimal_values(values: Sequence[Any]) -> Decimal:
    return sum(flatten_decimal_values(values), Decimal("0.00"))


def decimal_to_api_number(value: Decimal) -> float:
    return float(quantize_money(value))


SHORT_MONTH_LABELS = {
    1: "Янв",
    2: "Фев",
    3: "Мар",
    4: "Апр",
    5: "Май",
    6: "Июн",
    7: "Июл",
    8: "Авг",
    9: "Сен",
    10: "Окт",
    11: "Ноя",
    12: "Дек",
}
