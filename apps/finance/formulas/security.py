from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

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
from apps.finance.formulas.dsl import (
    ALLOWED_CONSTANTS,
    ALLOWED_FUNCTIONS,
    ALLOWED_SYSTEM_VARIABLES,
    BANNED_IDENTIFIERS,
    BANNED_KEYWORDS,
    BINARY_OPERATORS,
    UNARY_OPERATORS,
)

MAX_SECURITY_AST_NODES = 300
MAX_STRING_LITERAL_LENGTH = 500
MAX_IDENTIFIER_LENGTH = 80
MAX_NAMED_ARGUMENT_LENGTH = 40

RUNTIME_ALLOWED_FUNCTIONS = {
    "TRANSACTIONS",
    "BALANCE",
    "SUM",
    "AVG",
    "COUNT",
    "MIN",
    "MAX",
    "ROUND",
    "IF",
    "TODAY",
    "START_OF",
    "END_OF",
}

_ALLOWED_NODE_TYPES = (
    FormulaProgram,
    LetStatement,
    ReturnStatement,
    NumberExpression,
    StringExpression,
    LiteralExpression,
    VariableExpression,
    ConstantExpression,
    UnaryExpression,
    BinaryExpression,
    FunctionCallExpression,
    NamedArgument,
)


@dataclass(frozen=True)
class SecurityRule:
    id: str
    message_template: str


UNSAFE_IDENTIFIER_RULES = {
    "eval": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "exec": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "compile": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "open": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "input": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "globals": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "locals": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "vars": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "dir": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "super": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "getattr": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "setattr": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "delattr": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "__import__": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "os": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "sys": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "subprocess": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "pathlib": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "builtins": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "django": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
    "settings": SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул."),
}

SECURITY_BLOCKING_DIAGNOSTIC_IDS = {
    "unsafe-construct",
    "dunder-access-denied",
    "attribute-access-denied",
    "identifier-too-long",
}


def is_unsafe_identifier_value(value: str) -> bool:
    raw_value = str(value or "")
    return (
        raw_value.lower() in UNSAFE_IDENTIFIER_RULES
        or raw_value.lower() in BANNED_IDENTIFIERS
        or raw_value.upper() in BANNED_KEYWORDS
    )


def has_blocking_identifier_security_diagnostic(value: str) -> bool:
    return any(
        diagnostic.id in SECURITY_BLOCKING_DIAGNOSTIC_IDS
        for diagnostic in validate_identifier_token_security(value=value, line=1)
    )


def validate_code_security_preflight(code: str) -> list[FormulaDiagnostic]:
    """Check raw code-level restrictions before tokenization.

    This layer intentionally does not execute or parse expressions. It only
    catches payloads that are never valid for the financial DSL and should not
    reach deeper parser/evaluator code.
    """
    diagnostics: list[FormulaDiagnostic] = []
    for line_number, line in enumerate(str(code or "").splitlines() or [""], start=1):
        for char in line:
            if ord(char) < 32 and char not in "\t":
                diagnostics.append(
                    FormulaDiagnostic(
                        id="control-character-denied",
                        line=line_number,
                        message="Управляющие символы запрещены в DSL формул.",
                    )
                )
                break

        if "`" in line:
            diagnostics.append(
                FormulaDiagnostic(
                    id="unexpected-character",
                    line=line_number,
                    message="Символ ` не поддерживается в DSL формул.",
                )
            )
        if "@" in line:
            diagnostics.append(
                FormulaDiagnostic(
                    id="unexpected-character",
                    line=line_number,
                    message="Символ @ не поддерживается в DSL формул.",
                )
            )
        if any(char in line for char in "[]{}"):
            diagnostics.append(
                FormulaDiagnostic(
                    id="unsupported-construction",
                    line=line_number,
                    message="Списки, словари и индексный доступ не поддерживаются в DSL формул.",
                )
            )

        if len(diagnostics) >= MAX_DIAGNOSTICS:
            break

    return diagnostics[:MAX_DIAGNOSTICS]


def validate_identifier_token_security(*, value: str, line: int) -> list[FormulaDiagnostic]:
    diagnostics: list[FormulaDiagnostic] = []
    raw_value = str(value or "")
    lowered = raw_value.lower()
    uppered = raw_value.upper()

    if len(raw_value) > MAX_IDENTIFIER_LENGTH:
        diagnostics.append(
            FormulaDiagnostic(
                id="identifier-too-long",
                line=line,
                message=f"Идентификатор {raw_value[:40]}... слишком длинный.",
            )
        )

    if "__" in raw_value:
        diagnostics.append(
            FormulaDiagnostic(
                id="dunder-access-denied",
                line=line,
                message="Идентификаторы с двойным подчёркиванием запрещены в DSL формул.",
            )
        )

    if "." in raw_value:
        diagnostics.append(
            FormulaDiagnostic(
                id="attribute-access-denied",
                line=line,
                message="Доступ к атрибутам через точку не поддерживается в DSL формул.",
            )
        )

    rule = UNSAFE_IDENTIFIER_RULES.get(lowered)
    if rule is None and (lowered in BANNED_IDENTIFIERS or uppered in BANNED_KEYWORDS):
        rule = SecurityRule("unsafe-construct", "Конструкция {value} запрещена в DSL формул.")

    if rule is not None:
        diagnostics.append(
            FormulaDiagnostic(
                id=rule.id,
                line=line,
                message=rule.message_template.format(value=raw_value),
            )
        )

    return diagnostics[:MAX_DIAGNOSTICS]


def validate_program_security(program: FormulaProgram) -> list[FormulaDiagnostic]:
    diagnostics: list[FormulaDiagnostic] = []
    node_count = 0

    for node in walk_ast(program):
        node_count += 1
        if node_count > MAX_SECURITY_AST_NODES:
            diagnostics.append(
                FormulaDiagnostic(
                    id="formula-too-complex",
                    line=getattr(node, "line", 1),
                    message="Формула слишком сложная для безопасного выполнения.",
                )
            )
            break

        diagnostics.extend(validate_ast_node_security(node))
        if len(diagnostics) >= MAX_DIAGNOSTICS:
            break

    return diagnostics[:MAX_DIAGNOSTICS]


def validate_ast_node_security(node: AstNode) -> list[FormulaDiagnostic]:
    diagnostics: list[FormulaDiagnostic] = []
    line = getattr(node, "line", 1)

    if not isinstance(node, _ALLOWED_NODE_TYPES):
        return [
            FormulaDiagnostic(
                id="unsupported-construction",
                line=line,
                message="Неподдерживаемая конструкция формулы запрещена для выполнения.",
            )
        ]

    if isinstance(node, LetStatement):
        diagnostics.extend(validate_local_variable_name_security(name=node.name, line=node.line))

    if isinstance(node, VariableExpression):
        diagnostics.extend(validate_variable_reference_security(name=node.name, line=node.line))

    if isinstance(node, ConstantExpression) and node.name not in ALLOWED_CONSTANTS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unknown-constant",
                line=node.line,
                message=f"Неизвестная константа {node.name}.",
            )
        )

    if isinstance(node, FunctionCallExpression):
        diagnostics.extend(validate_function_call_name_security(name=node.name, line=node.line))

    if isinstance(node, NamedArgument):
        diagnostics.extend(validate_named_argument_security(name=node.name, line=node.line))

    if isinstance(node, UnaryExpression) and node.operator not in UNARY_OPERATORS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unsupported-operator",
                line=node.line,
                message=f"Оператор {node.operator} не поддерживается.",
            )
        )

    if isinstance(node, BinaryExpression) and node.operator not in BINARY_OPERATORS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unsupported-operator",
                line=node.line,
                message=f"Оператор {node.operator} не поддерживается.",
            )
        )

    if isinstance(node, StringExpression) and len(node.value) > MAX_STRING_LITERAL_LENGTH:
        diagnostics.append(
            FormulaDiagnostic(
                id="string-too-long",
                line=node.line,
                message=f"Строковый литерал не должен быть длиннее {MAX_STRING_LITERAL_LENGTH} символов.",
            )
        )

    return diagnostics[:MAX_DIAGNOSTICS]


def validate_function_call_name_security(*, name: str, line: int) -> list[FormulaDiagnostic]:
    diagnostics = validate_identifier_token_security(value=name, line=line)
    if any(diagnostic.id in SECURITY_BLOCKING_DIAGNOSTIC_IDS for diagnostic in diagnostics):
        return diagnostics[:MAX_DIAGNOSTICS]

    function_name = name.upper()
    if function_name not in ALLOWED_FUNCTIONS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unknown-function",
                line=line,
                message=f"Неизвестная функция {name}.",
            )
        )

    return diagnostics[:MAX_DIAGNOSTICS]


def validate_local_variable_name_security(*, name: str, line: int) -> list[FormulaDiagnostic]:
    diagnostics = validate_identifier_token_security(value=name, line=line)
    if name.startswith("$"):
        diagnostics.append(
            FormulaDiagnostic(
                id="invalid-variable-name",
                line=line,
                message="Имя локальной переменной не может начинаться с $.",
            )
        )
    upper_name = name.upper()
    if name == upper_name and (upper_name in ALLOWED_FUNCTIONS or upper_name in ALLOWED_CONSTANTS):
        diagnostics.append(
            FormulaDiagnostic(
                id="reserved-variable-name",
                line=line,
                message=f"Имя {name} зарезервировано и не может использоваться как переменная.",
            )
        )
    return diagnostics[:MAX_DIAGNOSTICS]


def validate_variable_reference_security(*, name: str, line: int) -> list[FormulaDiagnostic]:
    if name.startswith("$"):
        if name not in ALLOWED_SYSTEM_VARIABLES:
            return [
                FormulaDiagnostic(
                    id="unknown-variable",
                    line=line,
                    message=f"Неизвестная системная переменная {name}.",
                )
            ]
        return []
    return validate_identifier_token_security(value=name, line=line)


def validate_named_argument_security(*, name: str, line: int) -> list[FormulaDiagnostic]:
    diagnostics = validate_identifier_token_security(value=name, line=line)
    if len(name) > MAX_NAMED_ARGUMENT_LENGTH:
        diagnostics.append(
            FormulaDiagnostic(
                id="argument-name-too-long",
                line=line,
                message=f"Имя аргумента {name[:30]}... слишком длинное.",
            )
        )
    if name.upper() in BANNED_KEYWORDS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unsafe-construct",
                line=line,
                message=f"Конструкция {name} запрещена в DSL формул.",
            )
        )
    return diagnostics[:MAX_DIAGNOSTICS]


def walk_ast(root: AstNode) -> Iterable[AstNode]:
    queue: deque[AstNode] = deque([root])
    while queue:
        node = queue.popleft()
        yield node
        queue.extend(get_child_nodes(node))


def get_child_nodes(node: AstNode) -> list[AstNode]:
    if isinstance(node, FormulaProgram):
        children: list[AstNode] = list(node.statements)
        if node.return_statement is not None:
            children.append(node.return_statement)
        return children
    if isinstance(node, LetStatement):
        return [node.expression]
    if isinstance(node, ReturnStatement):
        return [node.expression]
    if isinstance(node, UnaryExpression):
        return [node.operand]
    if isinstance(node, BinaryExpression):
        return [node.left, node.right]
    if isinstance(node, FunctionCallExpression):
        return list(node.arguments)
    if isinstance(node, NamedArgument):
        return [node.expression]
    return []
