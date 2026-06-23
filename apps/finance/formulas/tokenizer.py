from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.finance.formulas.diagnostics import FormulaDiagnostic
from apps.finance.formulas.dsl import BANNED_IDENTIFIERS, BANNED_KEYWORDS


@dataclass(frozen=True)
class Token:
    type: str
    value: str
    line: int
    column: int
    start_index: int
    end_index: int


@dataclass(frozen=True)
class TokenizeResult:
    tokens: list[Token]
    diagnostics: list[FormulaDiagnostic]


KEYWORDS = {"LET", "RETURN"}
SINGLE_CHAR_TOKENS = {
    "(": "LPAREN",
    ")": "RPAREN",
    ",": "COMMA",
    ":": "COLON",
    ";": "SEMICOLON",
}
TWO_CHAR_OPERATORS = {"==", "!=", ">=", "<=", "&&", "||"}
ONE_CHAR_OPERATORS = {"+", "-", "*", "/", ">", "<"}


def tokenize_formula(code: str) -> TokenizeResult:
    tokens: list[Token] = []
    diagnostics: list[FormulaDiagnostic] = []

    index = 0
    line = 1
    column = 1
    length = len(code)

    while index < length:
        char = code[index]

        if char in " \t\r":
            index += 1
            column += 1
            continue

        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue

        if char == "/" and index + 1 < length and code[index + 1] == "/":
            while index < length and code[index] != "\n":
                index += 1
                column += 1
            continue

        start_index = index
        start_column = column

        if char in {'"', "'"}:
            token, index, line, column, error = read_string(
                code=code,
                quote=char,
                start_index=start_index,
                line=line,
                column=column,
            )
            tokens.append(token)
            if error:
                diagnostics.append(error)
            continue

        if char.isdigit():
            token, index, column, error = read_number(
                code=code,
                start_index=start_index,
                line=line,
                column=column,
            )
            tokens.append(token)
            if error:
                diagnostics.append(error)
            continue

        if char == "$":
            token, index, column = read_variable(
                code=code,
                start_index=start_index,
                line=line,
                column=column,
            )
            tokens.append(token)
            continue

        if is_identifier_start(char):
            token, index, column = read_identifier(
                code=code,
                start_index=start_index,
                line=line,
                column=column,
            )
            tokens.append(token)
            diagnostics.extend(validate_identifier_token(token))
            continue

        two_chars = code[index : index + 2]
        if two_chars in TWO_CHAR_OPERATORS:
            tokens.append(
                Token(
                    type="OPERATOR",
                    value=two_chars,
                    line=line,
                    column=start_column,
                    start_index=start_index,
                    end_index=start_index + 2,
                )
            )
            index += 2
            column += 2
            continue

        if char in ONE_CHAR_OPERATORS:
            tokens.append(
                Token(
                    type="OPERATOR",
                    value=char,
                    line=line,
                    column=start_column,
                    start_index=start_index,
                    end_index=start_index + 1,
                )
            )
            index += 1
            column += 1
            continue

        if char == "=":
            tokens.append(
                Token(
                    type="EQUALS",
                    value=char,
                    line=line,
                    column=start_column,
                    start_index=start_index,
                    end_index=start_index + 1,
                )
            )
            index += 1
            column += 1
            continue

        if char == ".":
            diagnostics.append(
                FormulaDiagnostic(
                    id="attribute-access-denied",
                    line=line,
                    message="Доступ к атрибутам через точку не поддерживается в DSL формул.",
                )
            )
            index += 1
            column += 1
            continue

        token_type = SINGLE_CHAR_TOKENS.get(char)
        if token_type:
            tokens.append(
                Token(
                    type=token_type,
                    value=char,
                    line=line,
                    column=start_column,
                    start_index=start_index,
                    end_index=start_index + 1,
                )
            )
            index += 1
            column += 1
            continue

        diagnostics.append(
            FormulaDiagnostic(
                id="unexpected-character",
                line=line,
                message=f"Недопустимый символ: {char}.",
            )
        )
        index += 1
        column += 1

    tokens.append(
        Token(
            type="EOF",
            value="",
            line=line,
            column=column,
            start_index=length,
            end_index=length,
        )
    )
    return TokenizeResult(tokens=tokens, diagnostics=diagnostics)


def read_string(*, code: str, quote: str, start_index: int, line: int, column: int):
    index = start_index + 1
    current_line = line
    current_column = column + 1
    chars: list[str] = []
    escaped = False

    while index < len(code):
        char = code[index]
        if escaped:
            chars.append(resolve_escape(char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return (
                Token(
                    type="STRING",
                    value="".join(chars),
                    line=line,
                    column=column,
                    start_index=start_index,
                    end_index=index + 1,
                ),
                index + 1,
                current_line,
                current_column + 1,
                None,
            )
        elif char == "\n":
            current_line += 1
            current_column = 0
            chars.append(char)
        else:
            chars.append(char)
        index += 1
        current_column += 1

    return (
        Token(
            type="STRING",
            value="".join(chars),
            line=line,
            column=column,
            start_index=start_index,
            end_index=index,
        ),
        index,
        current_line,
        current_column,
        FormulaDiagnostic(
            id="unterminated-string",
            line=line,
            message="Строка не закрыта кавычкой.",
        ),
    )


def read_number(*, code: str, start_index: int, line: int, column: int):
    index = start_index
    has_dot = False

    while index < len(code):
        char = code[index]
        if char.isdigit():
            index += 1
            continue
        if char == "." and not has_dot and index + 1 < len(code) and code[index + 1].isdigit():
            has_dot = True
            index += 1
            continue
        break

    value = code[start_index:index]
    error = None
    try:
        Decimal(value)
    except InvalidOperation:
        error = FormulaDiagnostic(
            id="invalid-number",
            line=line,
            message=f"Некорректное число: {value}.",
        )

    return (
        Token(
            type="NUMBER",
            value=value,
            line=line,
            column=column,
            start_index=start_index,
            end_index=index,
        ),
        index,
        column + (index - start_index),
        error,
    )


def read_variable(*, code: str, start_index: int, line: int, column: int):
    index = start_index + 1
    while index < len(code) and is_identifier_part(code[index]):
        index += 1

    return (
        Token(
            type="VARIABLE",
            value=code[start_index:index],
            line=line,
            column=column,
            start_index=start_index,
            end_index=index,
        ),
        index,
        column + (index - start_index),
    )


def read_identifier(*, code: str, start_index: int, line: int, column: int):
    index = start_index
    while index < len(code) and (is_identifier_part(code[index]) or code[index] == "."):
        index += 1

    raw_value = code[start_index:index]
    upper_value = raw_value.upper()

    if upper_value in KEYWORDS:
        token_type = "KEYWORD"
        value = upper_value
    elif upper_value in BANNED_KEYWORDS:
        token_type = "IDENTIFIER"
        value = raw_value
    else:
        token_type = "IDENTIFIER"
        value = raw_value

    return (
        Token(
            type=token_type,
            value=value,
            line=line,
            column=column,
            start_index=start_index,
            end_index=index,
        ),
        index,
        column + (index - start_index),
    )


def validate_identifier_token(token: Token) -> list[FormulaDiagnostic]:
    diagnostics: list[FormulaDiagnostic] = []
    value = token.value
    lowered = value.lower()
    uppered = value.upper()

    if "__" in value:
        diagnostics.append(
            FormulaDiagnostic(
                id="dunder-access-denied",
                line=token.line,
                message="Идентификаторы с двойным подчёркиванием запрещены в DSL формул.",
            )
        )

    if "." in value:
        diagnostics.append(
            FormulaDiagnostic(
                id="attribute-access-denied",
                line=token.line,
                message="Доступ к атрибутам через точку не поддерживается в DSL формул.",
            )
        )

    if lowered in BANNED_IDENTIFIERS or uppered in BANNED_KEYWORDS:
        diagnostics.append(
            FormulaDiagnostic(
                id="unsafe-construct",
                line=token.line,
                message=f"Конструкция {value} запрещена в DSL формул.",
            )
        )

    return diagnostics


def is_identifier_start(char: str) -> bool:
    return char == "_" or char.isalpha()


def is_identifier_part(char: str) -> bool:
    return char == "_" or char.isalpha() or char.isdigit()


def resolve_escape(char: str) -> str:
    return {
        "n": "\n",
        "r": "\r",
        "t": "\t",
        '"': '"',
        "'": "'",
        "\\": "\\",
    }.get(char, char)
