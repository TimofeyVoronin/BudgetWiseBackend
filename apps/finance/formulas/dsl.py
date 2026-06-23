from __future__ import annotations

ALLOWED_SYSTEM_VARIABLES = {
    "$period",
    "$start_date",
    "$end_date",
    "$month",
    "$year",
    "$account",
    "$accounts",
    "$currency",
}

ALLOWED_CONSTANTS = {
    "INCOME",
    "EXPENSE",
    "TRANSFER",
}

SUPPORTED_FUNCTIONS = {
    "TRANSACTIONS",
    "SUM",
    "AVG",
    "COUNT",
    "BALANCE",
    "ROUND",
    "START_OF",
    "END_OF",
    "TODAY",
}

FUTURE_FUNCTIONS = {
    "MIN",
    "MAX",
    "IF",
}

ALLOWED_FUNCTIONS = SUPPORTED_FUNCTIONS | FUTURE_FUNCTIONS

BANNED_IDENTIFIERS = {
    "eval",
    "exec",
    "compile",
    "import",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "super",
    "getattr",
    "setattr",
    "delattr",
    "__import__",
    "os",
    "sys",
    "subprocess",
    "pathlib",
    "builtins",
    "django",
    "settings",
}

BANNED_KEYWORDS = {
    "FOR",
    "WHILE",
    "DEF",
    "CLASS",
    "LAMBDA",
    "YIELD",
    "TRY",
    "EXCEPT",
    "FINALLY",
    "WITH",
    "ASYNC",
    "AWAIT",
    "DEL",
    "GLOBAL",
    "NONLOCAL",
}

BINARY_OPERATORS = {
    "||",
    "&&",
    "==",
    "!=",
    ">",
    "<",
    ">=",
    "<=",
    "+",
    "-",
    "*",
    "/",
}

UNARY_OPERATORS = {"+", "-"}

OPERATOR_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    ">": 3,
    "<": 3,
    ">=": 3,
    "<=": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
}

MAX_DIAGNOSTICS = 50
