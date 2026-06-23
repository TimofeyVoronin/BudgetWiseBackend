from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


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
    return FormulaValidationResult(tuple(diagnostics))
