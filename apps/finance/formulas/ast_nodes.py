from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class AstNode:
    line: int


@dataclass(frozen=True)
class FormulaProgram(AstNode):
    statements: list[AstNode] = field(default_factory=list)
    return_statement: ReturnStatement | None = None  # type: ignore[name-defined]


@dataclass(frozen=True)
class LetStatement(AstNode):
    name: str
    expression: AstNode


@dataclass(frozen=True)
class ReturnStatement(AstNode):
    expression: AstNode


@dataclass(frozen=True)
class BinaryExpression(AstNode):
    operator: str
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class UnaryExpression(AstNode):
    operator: str
    operand: AstNode


@dataclass(frozen=True)
class LiteralExpression(AstNode):
    value: Any


@dataclass(frozen=True)
class NumberExpression(LiteralExpression):
    value: Decimal


@dataclass(frozen=True)
class StringExpression(LiteralExpression):
    value: str


@dataclass(frozen=True)
class VariableExpression(AstNode):
    name: str


@dataclass(frozen=True)
class ConstantExpression(AstNode):
    name: str


@dataclass(frozen=True)
class NamedArgument(AstNode):
    name: str
    expression: AstNode


@dataclass(frozen=True)
class FunctionCallExpression(AstNode):
    name: str
    arguments: list[AstNode] = field(default_factory=list)
