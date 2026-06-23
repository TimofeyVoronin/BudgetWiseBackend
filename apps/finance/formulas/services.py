from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from apps.finance.formulas.constants import (
    DEFAULT_CONSTRUCTOR_BLOCKS,
    DEFAULT_FORMULA_CODE,
    FORMULA_ID_DEFAULT,
    FORMULA_IDE_META,
)
from apps.finance.models import FormulaIdeDraft


def get_formula_ide_state(*, user) -> dict[str, Any]:
    draft = FormulaIdeDraft.objects.filter(
        user=user,
        formula_id=FORMULA_ID_DEFAULT,
    ).first()

    if draft is None:
        return {
            "formula_id": FORMULA_ID_DEFAULT,
            "code": DEFAULT_FORMULA_CODE,
            "constructor_blocks": deepcopy(DEFAULT_CONSTRUCTOR_BLOCKS),
            "updated_at": None,
            "is_saved": False,
        }

    return build_formula_ide_state_payload(draft=draft)


def save_formula_ide_state(*, user, code: str, constructor_blocks: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    draft, _ = FormulaIdeDraft.objects.update_or_create(
        user=user,
        formula_id=FORMULA_ID_DEFAULT,
        defaults={
            "code": code,
            "constructor_blocks": normalize_constructor_blocks(constructor_blocks),
            "is_saved": True,
        },
    )

    return {
        "formula_id": draft.formula_id,
        "updated_at": draft.updated_at,
        "is_saved": draft.is_saved,
    }


def get_formula_ide_meta() -> dict[str, Any]:
    return deepcopy(FORMULA_IDE_META)


def build_formula_ide_state_payload(*, draft: FormulaIdeDraft) -> dict[str, Any]:
    return {
        "formula_id": draft.formula_id,
        "code": draft.code,
        "constructor_blocks": normalize_constructor_blocks(draft.constructor_blocks),
        "updated_at": draft.updated_at,
        "is_saved": draft.is_saved,
    }


def normalize_constructor_blocks(constructor_blocks: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if not constructor_blocks:
        return []

    normalized: list[dict[str, Any]] = []
    for block in constructor_blocks:
        normalized.append(
            {
                "id": str(block.get("id", "")),
                "kind": str(block.get("kind", "")),
                "label": str(block.get("label", "")),
            }
        )
    return normalized


def validate_formula_ide_code(*, code: str) -> dict[str, Any]:
    from apps.finance.formulas.parser import validate_formula_code

    return validate_formula_code(code).to_dict()
