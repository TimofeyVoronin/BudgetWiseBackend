from __future__ import annotations

from datetime import date
from typing import Iterable

from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError


TRUE_VALUES = {"true", "True", "1"}
FALSE_VALUES = {"false", "False", "0"}


def get_int_query_param(query_params, name: str) -> int | None:
    value = query_params.get(name)

    if value in (None, ""):
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise ValidationError(
            {name: "Параметр должен быть целым числом."}
        ) from exc


def get_bool_query_param(query_params, name: str) -> bool | None:
    value = query_params.get(name)

    if value in (None, ""):
        return None

    if value in TRUE_VALUES:
        return True

    if value in FALSE_VALUES:
        return False

    raise ValidationError(
        {name: "Параметр должен быть boolean: true или false."}
    )


def get_date_query_param(query_params, name: str) -> date | None:
    value = query_params.get(name)

    if value in (None, ""):
        return None

    parsed_value = parse_date(value)

    if parsed_value is None:
        raise ValidationError(
            {name: "Дата должна быть в формате YYYY-MM-DD."}
        )

    return parsed_value


def validate_choice_query_param(
    query_params,
    name: str,
    allowed_values: Iterable[str],
) -> str | None:
    value = query_params.get(name)

    if value in (None, ""):
        return None

    allowed_values = set(allowed_values)

    if value not in allowed_values:
        allowed_as_text = ", ".join(sorted(allowed_values))
        raise ValidationError(
            {name: f"Допустимые значения: {allowed_as_text}."}
        )

    return value


def validate_ordering(
    ordering: str | None,
    allowed_values: Iterable[str],
) -> str | None:
    if ordering in (None, ""):
        return None

    allowed_values = set(allowed_values)

    if ordering not in allowed_values:
        allowed_as_text = ", ".join(sorted(allowed_values))
        raise ValidationError(
            {"ordering": f"Допустимые значения: {allowed_as_text}."}
        )

    return ordering