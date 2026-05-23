from __future__ import annotations

from decimal import Decimal
from datetime import timedelta
from typing import Iterable

from django.db.models import Max, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.finance.currencies.services import (
    build_currency_select_options,
    get_user_default_currency_code,
    get_user_visible_currency_codes,
)
from apps.finance.models import (
    Account,
    Category,
    Tag,
    TransactionTemplate,
    TransactionTemplateStatus,
    TransactionType,
    normalize_tag_text,
)
from apps.finance.tags.services import get_accessible_tags, get_tag_ids_query_param


MAX_TEMPLATE_SEARCH_LENGTH = 100
MAX_TEMPLATE_PAGE_SIZE = 100
DEFAULT_TEMPLATE_PAGE_SIZE = 20
FREQUENT_TEMPLATE_MIN_USE_COUNT = 3

TEMPLATE_STATUS_VALUES = {
    TransactionTemplateStatus.ACTIVE,
    TransactionTemplateStatus.ARCHIVED,
}

TEMPLATE_SORT_FIELDS = {
    "name": "name",
    "useCount": "use_count",
    "use_count": "use_count",
    "lastUsedAt": "last_used_at",
    "last_used_at": "last_used_at",
    "createdAt": "created_at",
    "created_at": "created_at",
    "updatedAt": "updated_at",
    "updated_at": "updated_at",
}

TEMPLATE_SORT_DIRECTIONS = {"asc", "desc"}

TEMPLATE_KIND_OPTIONS = [
    {"title": "Расход", "value": TransactionType.EXPENSE},
    {"title": "Доход", "value": TransactionType.INCOME},
]

TEMPLATE_STATUS_OPTIONS = [
    {"title": "Активные", "value": TransactionTemplateStatus.ACTIVE},
    {"title": "Архив", "value": TransactionTemplateStatus.ARCHIVED},
]


def get_accessible_transaction_templates(user) -> QuerySet[TransactionTemplate]:
    if not user or not user.is_authenticated:
        return TransactionTemplate.objects.none()

    return (
        TransactionTemplate.objects
        .filter(user=user)
        .select_related("account", "category")
        .prefetch_related("tags__group")
    )


def transaction_template_duplicate_exists(
    *,
    user,
    name: str,
    exclude_id: int | None = None,
    status: str = TransactionTemplateStatus.ACTIVE,
) -> bool:
    normalized_name = normalize_tag_text(name)

    if not normalized_name:
        return False

    queryset = TransactionTemplate.objects.filter(
        user=user,
        normalized_name=normalized_name,
        status=status,
    )

    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)

    return queryset.exists()


def parse_multi_value_query_param(query_params, *names: str) -> list[str]:
    values: list[str] = []

    for name in names:
        if hasattr(query_params, "getlist"):
            raw_values = query_params.getlist(name) + query_params.getlist(f"{name}[]")
        else:
            value = query_params.get(name) if hasattr(query_params, "get") else None
            raw_values = value if isinstance(value, list) else [value]

        for raw_value in raw_values:
            if raw_value in (None, ""):
                continue

            values.extend(
                item.strip()
                for item in str(raw_value).split(",")
                if item.strip()
            )

        if values:
            break

    return values


def parse_multi_int_query_param(query_params, *names: str) -> list[int]:
    values = parse_multi_value_query_param(query_params, *names)
    used_name = names[0] if names else "ids"
    result: list[int] = []

    for value in values:
        try:
            parsed_value = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {used_name: ["Значения фильтра должны быть целыми числами."]}
            ) from exc

        if parsed_value <= 0:
            raise ValidationError(
                {used_name: ["ID должен быть положительным целым числом."]}
            )

        result.append(parsed_value)

    return list(dict.fromkeys(result))


def get_first_query_value(query_params, *names: str):
    for name in names:
        value = query_params.get(name)

        if value not in (None, ""):
            return value

    return None


def get_positive_int_query_param(query_params, *names: str, default: int) -> int:
    raw_value = get_first_query_value(query_params, *names)

    if raw_value in (None, ""):
        return default

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError({names[0]: ["Значение должно быть целым числом."]}) from exc

    if value <= 0:
        raise ValidationError({names[0]: ["Значение должно быть больше нуля."]})

    return value


def get_template_ordering(query_params) -> list[str]:
    ordering = query_params.get("ordering")

    if ordering:
        result = []

        for raw_field in str(ordering).split(","):
            field = raw_field.strip()
            direction = ""

            if not field:
                continue

            if field.startswith("-"):
                direction = "-"
                field = field[1:]

            if field not in TEMPLATE_SORT_FIELDS:
                raise ValidationError(
                    {
                        "ordering": [
                            "Недопустимое поле сортировки шаблонов."
                        ]
                    }
                )

            result.append(f"{direction}{TEMPLATE_SORT_FIELDS[field]}")

        return result or ["name", "id"]

    sort_by = query_params.get("sortBy") or query_params.get("sort_by") or "name"

    if sort_by not in TEMPLATE_SORT_FIELDS:
        raise ValidationError(
            {
                "sortBy": [
                    "Допустимые значения: name, useCount, lastUsedAt, createdAt, updatedAt."
                ]
            }
        )

    sort_order = query_params.get("sortOrder") or query_params.get("sort_order") or "asc"

    if sort_order not in TEMPLATE_SORT_DIRECTIONS:
        raise ValidationError(
            {"sortOrder": ["Направление сортировки должно быть asc или desc."]}
        )

    field = TEMPLATE_SORT_FIELDS[sort_by]

    if sort_order == "desc":
        field = f"-{field}"

    return [field, "name", "id"]


def filter_transaction_templates_queryset(queryset, request) -> QuerySet[TransactionTemplate]:
    query_params = request.query_params

    status = query_params.get("status")
    if status in (None, ""):
        status = TransactionTemplateStatus.ACTIVE

    if status not in TEMPLATE_STATUS_VALUES:
        raise ValidationError(
            {"status": ["Допустимые значения: active или archived."]}
        )

    queryset = queryset.filter(status=status)

    search = query_params.get("search")

    if search:
        search = search.strip()

        if len(search) > MAX_TEMPLATE_SEARCH_LENGTH:
            raise ValidationError(
                {"search": [f"Поиск не может быть длиннее {MAX_TEMPLATE_SEARCH_LENGTH} символов."]}
            )

        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(note__icontains=search)
            | Q(category__name__icontains=search)
            | Q(account__name__icontains=search)
            | Q(tags__name__icontains=search)
        )

    category_ids = parse_multi_int_query_param(query_params, "categories", "categoryIds", "category_ids")
    if category_ids:
        _validate_ids_belong_to_user(
            model=Category,
            user=request.user,
            ids=category_ids,
            field_name="categories",
            message="Некоторые категории не найдены или недоступны текущему пользователю.",
        )
        queryset = queryset.filter(category_id__in=category_ids)

    account_ids = parse_multi_int_query_param(query_params, "accounts", "accountIds", "account_ids")
    if account_ids:
        _validate_ids_belong_to_user(
            model=Account,
            user=request.user,
            ids=account_ids,
            field_name="accounts",
            message="Некоторые счета не найдены или недоступны текущему пользователю.",
        )
        queryset = queryset.filter(account_id__in=account_ids)

    tag_ids = get_tag_ids_query_param(query_params, "tagIds", "tags", "tag_ids")
    if tag_ids:
        accessible_tag_ids = set(
            get_accessible_tags(request.user).filter(pk__in=tag_ids).values_list("id", flat=True)
        )
        missing_ids = [tag_id for tag_id in tag_ids if tag_id not in accessible_tag_ids]

        if missing_ids:
            raise ValidationError(
                {"tagIds": ["Некоторые теги не найдены или недоступны текущему пользователю."]}
            )

        queryset = queryset.filter(tags__id__in=tag_ids)

    tag_query = query_params.get("tagQuery") or query_params.get("tag_query")
    if tag_query:
        tag_query = tag_query.strip()

        if len(tag_query) > MAX_TEMPLATE_SEARCH_LENGTH:
            raise ValidationError(
                {"tagQuery": [f"Поиск по тегам не может быть длиннее {MAX_TEMPLATE_SEARCH_LENGTH} символов."]}
            )

        queryset = queryset.filter(tags__name__icontains=tag_query)

    return queryset.distinct().order_by(*get_template_ordering(query_params))


def _validate_ids_belong_to_user(*, model, user, ids: Iterable[int], field_name: str, message: str) -> None:
    available_ids = set(model.objects.filter(user=user, pk__in=ids).values_list("id", flat=True))
    missing_ids = [item_id for item_id in ids if item_id not in available_ids]

    if missing_ids:
        raise ValidationError({field_name: [message]})


def build_transaction_templates_summary(queryset) -> dict:
    total_count = queryset.count()
    frequent_count = queryset.filter(use_count__gte=FREQUENT_TEMPLATE_MIN_USE_COUNT).count()
    last_used_at = queryset.aggregate(last_used=Max("last_used_at"))["last_used"]

    return {
        "totalCount": total_count,
        "frequentCount": frequent_count,
        "lastUsedLabel": format_last_used_label(last_used_at),
    }


def format_last_used_label(value) -> str:
    if not value:
        return "Нет данных"

    local_value = timezone.localtime(value)
    today = timezone.localdate()

    if local_value.date() == today:
        return "Сегодня"

    if local_value.date() == today - timedelta(days=1):
        return "Вчера"

    return local_value.strftime("%d.%m.%Y")


def get_transaction_templates_meta_payload(user) -> dict:
    return {
        "kinds": TEMPLATE_KIND_OPTIONS,
        "statuses": TEMPLATE_STATUS_OPTIONS,
        "defaultCurrency": get_user_default_currency_code(user),
        "currencies": build_currency_select_options(user),
        "categories": [
            {
                "title": category.name,
                "value": category.pk,
                "icon": category.icon,
                "color": category.color,
                "kind": category.type,
            }
            for category in Category.objects.filter(
                user=user,
                is_active=True,
                is_archived=False,
            ).order_by("type", "name", "id")
        ],
        "accounts": [
            {
                "title": account.name,
                "value": account.pk,
                "icon": account.icon,
                "currency": account.currency,
            }
            for account in Account.objects.filter(
                user=user,
                is_active=True,
                is_archived=False,
                currency__in=get_user_visible_currency_codes(user),
            ).order_by("-is_default", "name", "id")
        ],
        "sortOptions": [
            {"title": "По названию", "value": "name"},
            {"title": "По частоте использования", "value": "useCount"},
            {"title": "По последнему применению", "value": "lastUsedAt"},
        ],
    }
