from __future__ import annotations

import re

from django.db.models import Count, Q, QuerySet, Value, IntegerField

from apps.finance.models import Tag, TagGroup, normalize_tag_text


MAX_TAG_SEARCH_LENGTH = 100
MAX_TAG_PAGE_SIZE = 100
MAX_TAG_NAME_LENGTH = 80
MAX_TAG_ICON_LENGTH = 50
MAX_TAG_DESCRIPTION_LENGTH = 500
DEFAULT_TAG_COLOR = "#4F46E5"
DEFAULT_TAG_ICON = "tag"

TAG_COLOR_OPTIONS = [
    {"title": "Зелёный", "value": "#66BB6A"},
    {"title": "Синий", "value": "#42A5F5"},
    {"title": "Оранжевый", "value": "#FFA726"},
    {"title": "Фиолетовый", "value": "#AB47BC"},
    {"title": "Красный", "value": "#EF5350"},
    {"title": "Бирюзовый", "value": "#26A69A"},
    {"title": "Индиго", "value": "#5C6BC0"},
    {"title": "Розовый", "value": "#EC407A"},
    {"title": "Пурпурный", "value": "#7E57C2"},
    {"title": "Голубой", "value": "#26C6DA"},
    {"title": "Серый", "value": "#9E9E9E"},
    {"title": "Коричневый", "value": "#8D6E63"},
]

TAG_ICON_OPTIONS = [
    {"title": "Тег", "value": "tag"},
    {"title": "Покупки", "value": "cart"},
    {"title": "Кофе", "value": "coffee"},
    {"title": "Авто", "value": "car"},
    {"title": "Подарок", "value": "gift"},
    {"title": "Работа", "value": "briefcase"},
    {"title": "Дом", "value": "home"},
    {"title": "Такси", "value": "taxi"},
    {"title": "Еда", "value": "food"},
    {"title": "Здоровье", "value": "medical-bag"},
    {"title": "Топливо", "value": "gas-station"},
    {"title": "Ноутбук", "value": "laptop"},
    {"title": "Отпуск", "value": "beach"},
    {"title": "Перевод", "value": "swap-horizontal"},
    {"title": "Избранное", "value": "heart"},
    {"title": "Звезда", "value": "star"},
]

TAG_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TAG_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
TAG_NAME_RE = re.compile(r"^[\w\s\-.,&()+№]+$", re.UNICODE)

TAG_ALLOWED_ICON_VALUES = {option["value"] for option in TAG_ICON_OPTIONS}

TAG_SORT_FIELDS = {
    "name": "name",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "isVisible": "is_visible",
    "operationsCount": "operations_count",
}

TAG_SORT_ORDERS = {
    "asc",
    "desc",
    "asc-nulls-first",
    "desc-nulls-first",
    "asc-nulls-last",
    "desc-nulls-last",
}


def get_accessible_tag_groups(user) -> QuerySet[TagGroup]:
    if not user or not user.is_authenticated:
        return TagGroup.objects.none()

    return TagGroup.objects.filter(
        Q(user=user) | Q(is_system=True)
    )


def get_accessible_tags(user) -> QuerySet[Tag]:
    if not user or not user.is_authenticated:
        return Tag.objects.none()

    queryset = (
        Tag.objects
        .select_related("group")
        .filter(Q(user=user) | Q(is_system=True))
    )

    if hasattr(Tag, "transactions"):
        return queryset.annotate(operations_count=Count("transactions", distinct=True))

    return queryset.annotate(operations_count=Value(0, output_field=IntegerField()))


def get_tag_group_options(user) -> list[dict]:
    groups = get_accessible_tag_groups(user).order_by("is_system", "name", "id")

    return [
        {
            "id": group.pk,
            "name": group.name,
        }
        for group in groups
    ]


def build_tags_summary(queryset) -> dict:
    aggregate = queryset.aggregate(total_count=Count("id"))
    total_count = aggregate["total_count"] or 0
    with_operations_count = queryset.filter(operations_count__gt=0).count()

    return {
        "totalCount": total_count,
        "withOperationsCount": with_operations_count,
        "withoutOperationsCount": max(total_count - with_operations_count, 0),
    }


def tag_duplicate_exists(*, user, name: str, exclude_id: int | None = None) -> bool:
    normalized_name = normalize_tag_text(name)

    if not normalized_name:
        return False

    queryset = Tag.objects.filter(
        Q(user=user) | Q(is_system=True),
        normalized_name=normalized_name,
    )

    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)

    return queryset.exists()

def normalize_tag_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def get_tag_operations_count(tag: Tag) -> int:
    annotated_count = getattr(tag, "operations_count", None)

    if annotated_count is not None:
        return int(annotated_count or 0)

    transactions = getattr(tag, "transactions", None)

    if transactions is not None and hasattr(transactions, "count"):
        return int(transactions.count())

    return 0


def is_valid_tag_name(value: str) -> bool:
    normalized_value = normalize_tag_name(value)

    if not normalized_value:
        return False

    if len(normalized_value) > MAX_TAG_NAME_LENGTH:
        return False

    return bool(TAG_NAME_RE.fullmatch(normalized_value))


def is_valid_tag_color(value: str) -> bool:
    return bool(TAG_HEX_COLOR_RE.fullmatch(str(value or "").strip()))


def normalize_tag_color(value: str) -> str:
    return str(value or "").strip().upper()


def is_valid_tag_icon(value: str) -> bool:
    normalized_value = str(value or "").strip()

    if not normalized_value or len(normalized_value) > MAX_TAG_ICON_LENGTH:
        return False

    if not TAG_ICON_RE.fullmatch(normalized_value):
        return False

    return normalized_value in TAG_ALLOWED_ICON_VALUES

