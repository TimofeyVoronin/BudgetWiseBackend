from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

MAX_DIAGNOSTICS = 50


@dataclass(frozen=True)
class FormulaDiagnostic:
    """Diagnostic item shown in the formula IDE error panel."""

    id: str
    line: int
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "line": max(1, int(self.line or 1)),
            "message": self.message,
            "severity": self.severity or "error",
        }


@dataclass(frozen=True)
class FormulaValidationResult:
    """Result of safe DSL validation without formula execution."""

    diagnostics: tuple[FormulaDiagnostic, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [diagnostic.to_dict() for diagnostic in self.diagnostics]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
        }


def normalize_diagnostic(diagnostic: FormulaDiagnostic | dict[str, Any]) -> FormulaDiagnostic:
    if isinstance(diagnostic, FormulaDiagnostic):
        return diagnostic
    return FormulaDiagnostic(**diagnostic)


def diagnostic_key(diagnostic: FormulaDiagnostic) -> tuple[str, int, str]:
    return (
        diagnostic.id,
        max(1, int(diagnostic.line or 1)),
        diagnostic.message,
    )


def deduplicate_diagnostics(
    diagnostics: Iterable[FormulaDiagnostic | dict[str, Any]],
    *,
    limit: int = MAX_DIAGNOSTICS,
) -> list[FormulaDiagnostic]:
    result: list[FormulaDiagnostic] = []
    seen: set[tuple[str, int, str]] = set()
    truncated = False

    for diagnostic in diagnostics:
        item = normalize_diagnostic(diagnostic)
        key = diagnostic_key(item)
        if key in seen:
            continue
        seen.add(key)
        if len(result) >= limit:
            truncated = True
            break
        result.append(item)

    if truncated and limit > 0:
        result = result[: max(0, limit - 1)]
        result.append(
            FormulaDiagnostic(
                id="too-many-errors",
                line=1,
                message=f"Показаны первые {limit} ошибок. Исправьте их и повторите проверку.",
                severity="warning",
            )
        )

    return result


def build_validation_result(diagnostics: Iterable[FormulaDiagnostic | dict[str, Any]]) -> FormulaValidationResult:
    normalized = deduplicate_diagnostics(diagnostics)
    return FormulaValidationResult(tuple(normalized))
