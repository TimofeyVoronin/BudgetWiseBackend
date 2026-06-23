from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
from apps.finance.formulas.constants import MAX_FORMULA_CODE_LENGTH
from apps.finance.formulas.diagnostics import (
    FormulaDiagnostic,
    FormulaValidationResult,
    MAX_DIAGNOSTICS,
    build_validation_result,
)
from apps.finance.formulas.dsl import (
    ALLOWED_CONSTANTS,
    ALLOWED_FUNCTIONS,
    ALLOWED_SYSTEM_VARIABLES,
    OPERATOR_PRECEDENCE,
    UNARY_OPERATORS,
)
from apps.finance.formulas.security import (
    has_blocking_identifier_security_diagnostic,
    validate_code_security_preflight,
    validate_program_security,
)
from apps.finance.formulas.tokenizer import Token, tokenize_formula


class FormulaParser:
    """Safe DSL parser used only for syntax and constraint diagnostics."""

    def __init__(self, tokens: list[Token], diagnostics: list[FormulaDiagnostic] | None = None):
        self.tokens = tokens
        self.position = 0
        self.diagnostics: list[FormulaDiagnostic] = list(diagnostics or [])
        self.local_variables: set[str] = set()
        self.return_statement: ReturnStatement | None = None
        self.statements: list[AstNode] = []

    def parse(self) -> FormulaProgram:
        while not self.is_at_end():
            if self.match_keyword("LET"):
                statement = self.parse_let_statement()
                if statement is not None:
                    self.statements.append(statement)
                continue

            if self.match_keyword("RETURN"):
                if self.return_statement is not None:
                    self.add_diagnostic(
                        id="duplicate-return",
                        line=self.previous().line,
                        message="В формуле допускается только один оператор RETURN.",
                    )
                    self.synchronize_statement()
                    continue
                self.return_statement = self.parse_return_statement()
                continue

            token = self.peek()
            if token.type == "EOF":
                break

            self.add_diagnostic(
                id="unexpected-statement",
                line=token.line,
                message="Ожидался оператор LET или RETURN.",
            )
            self.synchronize_statement()

        if self.return_statement is None:
            last_token = self.previous() if self.position > 0 else self.peek()
            self.add_diagnostic(
                id="missing-return",
                line=last_token.line,
                message="В формуле должен быть оператор RETURN.",
            )

        return FormulaProgram(
            line=1,
            statements=self.statements,
            return_statement=self.return_statement,
        )

    def parse_let_statement(self) -> LetStatement | None:
        keyword = self.previous()
        name_token = self.consume("IDENTIFIER", "Ожидалось имя переменной после LET.", id="missing-variable-name")
        if name_token is None:
            self.synchronize_statement()
            return None

        variable_name = name_token.value
        self.validate_local_variable_declaration(token=name_token)

        self.consume("EQUALS", "Ожидался знак = после имени переменной.", id="missing-equals")
        expression = self.parse_expression()
        self.consume("SEMICOLON", "Ожидалась точка с запятой после объявления LET.", id="missing-semicolon")

        if self.is_safe_local_variable_name(variable_name):
            self.local_variables.add(variable_name)

        return LetStatement(
            line=keyword.line,
            name=variable_name,
            expression=expression,
        )

    def parse_return_statement(self) -> ReturnStatement:
        keyword = self.previous()
        expression = self.parse_expression()
        self.consume("SEMICOLON", "Ожидалась точка с запятой после RETURN.", id="missing-semicolon")
        return ReturnStatement(line=keyword.line, expression=expression)

    def parse_expression(self, min_precedence: int = 1) -> AstNode:
        expression = self.parse_unary()

        while True:
            token = self.peek()
            if token.type != "OPERATOR":
                break

            precedence = OPERATOR_PRECEDENCE.get(token.value)
            if precedence is None or precedence < min_precedence:
                break

            operator_token = self.advance()
            right = self.parse_expression(precedence + 1)
            expression = BinaryExpression(
                line=operator_token.line,
                operator=operator_token.value,
                left=expression,
                right=right,
            )

        return expression

    def parse_unary(self) -> AstNode:
        if self.peek().type == "OPERATOR" and self.peek().value in UNARY_OPERATORS:
            operator_token = self.advance()
            operand = self.parse_unary()
            return UnaryExpression(
                line=operator_token.line,
                operator=operator_token.value,
                operand=operand,
            )

        return self.parse_primary()

    def parse_primary(self) -> AstNode:
        token = self.peek()

        if self.match("NUMBER"):
            try:
                number = Decimal(token.value)
            except InvalidOperation:
                number = Decimal("0")
            return NumberExpression(line=token.line, value=number)

        if self.match("STRING"):
            return StringExpression(line=token.line, value=token.value)

        if self.match("VARIABLE"):
            self.validate_system_variable(token)
            return VariableExpression(line=token.line, name=token.value)

        if self.match("IDENTIFIER"):
            if self.match("LPAREN"):
                return self.parse_function_call(name_token=token)
            return self.parse_identifier_expression(token)

        if self.match("LPAREN"):
            expression = self.parse_expression()
            if not self.match("RPAREN"):
                self.add_diagnostic(
                    id="unclosed-bracket",
                    line=token.line,
                    message="Незакрытая скобка в выражении.",
                )
            return expression

        if self.match("KEYWORD"):
            self.add_diagnostic(
                id="unexpected-keyword",
                line=token.line,
                message=f"Ключевое слово {token.value} нельзя использовать внутри выражения.",
            )
            return LiteralExpression(line=token.line, value=None)

        self.add_diagnostic(
            id="expected-expression",
            line=token.line,
            message="Ожидалось выражение.",
        )
        if not self.is_at_end():
            self.advance()
        return LiteralExpression(line=token.line, value=None)

    def parse_identifier_expression(self, token: Token) -> AstNode:
        value = token.value
        upper_value = value.upper()

        # Local variables must have priority over constants. Otherwise a user
        # variable named "income" would be parsed as the INCOME constant, which
        # breaks formulas like "LET income = ...; RETURN income;".
        if value in self.local_variables:
            return VariableExpression(line=token.line, name=value)

        # Constants are intentionally uppercase-only in the DSL. Lowercase names
        # such as "income" are treated as user variables and should produce an
        # unknown-variable diagnostic if they were not declared.
        if value == upper_value and upper_value in ALLOWED_CONSTANTS:
            return ConstantExpression(line=token.line, name=upper_value)

        if not has_blocking_identifier_security_diagnostic(value):
            self.add_diagnostic(
                id="unknown-variable",
                line=token.line,
                message=f"Неизвестная переменная {value}.",
            )

        return VariableExpression(line=token.line, name=value)

    def parse_function_call(self, *, name_token: Token) -> FunctionCallExpression:
        function_name = name_token.value.upper()
        arguments: list[AstNode] = []

        if (
            function_name not in ALLOWED_FUNCTIONS
            and not has_blocking_identifier_security_diagnostic(name_token.value)
        ):
            self.add_diagnostic(
                id="unknown-function",
                line=name_token.line,
                message=f"Неизвестная функция {name_token.value}.",
            )

        if not self.check("RPAREN"):
            while True:
                if self.check_named_argument():
                    arg_name = self.advance()
                    self.consume("COLON", "Ожидалось двоеточие после имени аргумента.", id="missing-colon")
                    arg_expression = self.parse_expression()
                    arguments.append(NamedArgument(line=arg_name.line, name=arg_name.value, expression=arg_expression))
                else:
                    arguments.append(self.parse_expression())

                if not self.match("COMMA"):
                    break

                if self.check("RPAREN"):
                    self.add_diagnostic(
                        id="trailing-comma",
                        line=self.previous().line,
                        message="Лишняя запятая перед закрывающей скобкой.",
                    )
                    break

        if not self.match("RPAREN"):
            self.add_diagnostic(
                id="unclosed-bracket",
                line=name_token.line,
                message=f"Незакрытая скобка в вызове функции {name_token.value}.",
            )
            self.synchronize_expression()

        return FunctionCallExpression(
            line=name_token.line,
            name=name_token.value,
            arguments=arguments,
        )

    def validate_local_variable_declaration(self, *, token: Token) -> None:
        name = token.value
        upper_name = name.upper()

        if not self.is_safe_local_variable_name(name):
            self.add_diagnostic(
                id="invalid-variable-name",
                line=token.line,
                message=f"Некорректное имя переменной {name}.",
            )
            return

        if name == upper_name and (upper_name in ALLOWED_CONSTANTS or upper_name in ALLOWED_FUNCTIONS):
            self.add_diagnostic(
                id="reserved-variable-name",
                line=token.line,
                message=f"Имя {name} зарезервировано и не может использоваться как переменная.",
            )

        if name in self.local_variables:
            self.add_diagnostic(
                id="duplicate-variable",
                line=token.line,
                message=f"Переменная {name} уже объявлена.",
            )

    def validate_system_variable(self, token: Token) -> None:
        if token.value not in ALLOWED_SYSTEM_VARIABLES:
            self.add_diagnostic(
                id="unknown-variable",
                line=token.line,
                message=f"Неизвестная системная переменная {token.value}.",
            )

    def is_safe_local_variable_name(self, name: str) -> bool:
        if not name:
            return False
        if "." in name or "__" in name or name.startswith("$"):
            return False
        return name[0].isalpha() or name[0] == "_"

    def check_named_argument(self) -> bool:
        return self.peek().type == "IDENTIFIER" and self.peek_next().type == "COLON"

    def consume(self, token_type: str, message: str, *, id: str) -> Token | None:
        if self.check(token_type):
            return self.advance()

        self.add_diagnostic(
            id=id,
            line=self.peek().line,
            message=message,
        )
        return None

    def match_keyword(self, keyword: str) -> bool:
        if self.peek().type == "KEYWORD" and self.peek().value == keyword:
            self.advance()
            return True
        return False

    def match(self, token_type: str) -> bool:
        if self.check(token_type):
            self.advance()
            return True
        return False

    def check(self, token_type: str) -> bool:
        return self.peek().type == token_type

    def advance(self) -> Token:
        if not self.is_at_end():
            self.position += 1
        return self.previous()

    def previous(self) -> Token:
        return self.tokens[self.position - 1]

    def peek(self) -> Token:
        return self.tokens[self.position]

    def peek_next(self) -> Token:
        if self.position + 1 >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.position + 1]

    def is_at_end(self) -> bool:
        return self.peek().type == "EOF"

    def add_diagnostic(self, *, id: str, line: int, message: str, severity: str = "error") -> None:
        if len(self.diagnostics) >= MAX_DIAGNOSTICS:
            return
        self.diagnostics.append(FormulaDiagnostic(id=id, line=line, message=message, severity=severity))

    def synchronize_statement(self) -> None:
        while not self.is_at_end():
            if self.previous().type == "SEMICOLON":
                return
            if self.peek().type == "KEYWORD" and self.peek().value in {"LET", "RETURN"}:
                return
            self.advance()

    def synchronize_expression(self) -> None:
        while not self.is_at_end() and not self.check("SEMICOLON") and not self.check("COMMA") and not self.check("RPAREN"):
            self.advance()


def parse_formula_code(code: str) -> tuple[FormulaProgram, FormulaValidationResult]:
    preflight_diagnostics = validate_formula_code_preflight(code)
    if preflight_diagnostics:
        return (
            FormulaProgram(line=1, statements=[], return_statement=None),
            build_validation_result(preflight_diagnostics),
        )

    tokenize_result = tokenize_formula(code)
    parser = FormulaParser(tokens=tokenize_result.tokens, diagnostics=tokenize_result.diagnostics)
    program = parser.parse()
    security_diagnostics = validate_program_security(program)
    return program, build_validation_result([*parser.diagnostics, *security_diagnostics])


def validate_formula_code(code: str) -> FormulaValidationResult:
    _, result = parse_formula_code(code)
    return result


def validate_formula_code_preflight(code: str) -> list[FormulaDiagnostic]:
    if code is None:
        return [
            FormulaDiagnostic(
                id="empty-code",
                line=1,
                message="Код формулы не может быть пустым.",
            )
        ]

    if len(code) > MAX_FORMULA_CODE_LENGTH:
        return [
            FormulaDiagnostic(
                id="formula-too-long",
                line=1,
                message=f"Формула не должна быть длиннее {MAX_FORMULA_CODE_LENGTH} символов.",
            )
        ]

    if not code.strip():
        return [
            FormulaDiagnostic(
                id="empty-code",
                line=1,
                message="Код формулы не может быть пустым.",
            )
        ]

    return validate_code_security_preflight(code)
