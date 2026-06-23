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


def build_validation_result(diagnostics: Iterable[FormulaDiagnostic]) -> FormulaValidationResult:
    normalized: list[FormulaDiagnostic] = []
    seen: set[tuple[str, int, str]] = set()

    for diagnostic in diagnostics:
        item = diagnostic if isinstance(diagnostic, FormulaDiagnostic) else FormulaDiagnostic(**diagnostic)
        key = (item.id, max(1, int(item.line or 1)), item.message)
        if key in seen:
            continue
        seen.add(key)
        if len(normalized) >= MAX_DIAGNOSTICS:
            break
        normalized.append(item)

    if len(normalized) >= MAX_DIAGNOSTICS:
        limit_message = f"Показаны первые {MAX_DIAGNOSTICS} ошибок. Исправьте их и повторите проверку."
        limit_key = ("too-many-errors", 1, limit_message)
        if limit_key not in seen:
            normalized = normalized[: max(0, MAX_DIAGNOSTICS - 1)]
            normalized.append(
                FormulaDiagnostic(
                    id="too-many-errors",
                    line=1,
                    message=limit_message,
                    severity="warning",
                )
            )

    return FormulaValidationResult(tuple(normalized))
