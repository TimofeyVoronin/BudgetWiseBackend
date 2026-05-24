from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from django.db import transaction

from apps.finance.models import Category, Receipt, ReceiptItem, TransactionType
from apps.finance.receipts.provider import FiscalReceiptDetails, ReceiptLineItem

MONEY_QUANT = Decimal("0.01")
QUANTITY_QUANT = Decimal("0.001")
CONFIDENCE_QUANT = Decimal("0.01")

_NORMALIZE_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")

CATEGORY_KEYWORD_GROUPS: tuple[dict[str, tuple[str, ...]], ...] = (
    {
        "aliases": (
            "продукты",
            "еда",
            "супермаркеты",
            "магазины",
            "покупки",
            "продовольствие",
        ),
        "keywords": (
            "молоко",
            "хлеб",
            "сыр",
            "йогурт",
            "кефир",
            "творог",
            "масло",
            "мясо",
            "курица",
            "рыба",
            "яйцо",
            "яйца",
            "колбаса",
            "сосиски",
            "крупа",
            "рис",
            "гречка",
            "макароны",
            "картофель",
            "овощи",
            "фрукты",
            "яблоко",
            "банан",
            "сахар",
            "соль",
            "чай",
            "кофе",
            "вода",
            "сок",
            "печенье",
            "шоколад",
            "пятерочка",
            "магнит",
            "лента",
            "перекресток",
            "ашан",
        ),
    },
    {
        "aliases": ("кафе", "рестораны", "кофейни", "общепит", "еда вне дома"),
        "keywords": (
            "капучино",
            "латте",
            "эспрессо",
            "американо",
            "бургер",
            "пицца",
            "ролл",
            "суши",
            "обед",
            "ланч",
            "шаурма",
            "кафе",
            "ресторан",
            "кофейня",
        ),
    },
    {
        "aliases": ("транспорт", "такси", "авто", "автомобиль"),
        "keywords": (
            "такси",
            "яндекс go",
            "uber",
            "автобус",
            "метро",
            "проезд",
            "билет",
            "парковка",
            "азс",
            "бензин",
            "дизель",
            "топливо",
            "литр",
        ),
    },
    {
        "aliases": ("здоровье", "аптека", "медицина", "лекарства"),
        "keywords": (
            "аптека",
            "лекарство",
            "таблетки",
            "капсулы",
            "сироп",
            "витамины",
            "парацетамол",
            "ибупрофен",
            "анальгин",
            "пластырь",
        ),
    },
    {
        "aliases": ("одежда", "обувь", "гардероб"),
        "keywords": (
            "футболка",
            "джинсы",
            "куртка",
            "платье",
            "кроссовки",
            "ботинки",
            "обувь",
            "носки",
            "рубашка",
        ),
    },
    {
        "aliases": ("дом", "жилье", "хозтовары", "быт"),
        "keywords": (
            "чистящее",
            "порошок",
            "салфетки",
            "губка",
            "лампа",
            "батарейки",
            "посуда",
            "полотенце",
            "хозтовары",
        ),
    },
    {
        "aliases": ("развлечения", "досуг", "кино", "игры"),
        "keywords": (
            "кино",
            "театр",
            "билет",
            "игра",
            "подписка",
            "netflix",
            "spotify",
            "youtube",
            "музыка",
        ),
    },
)


@dataclass(frozen=True)
class ReceiptItemMappingSuggestion:
    category: Category | None
    confidence: Decimal
    reason: str
    matched_keyword: str = ""


@dataclass(frozen=True)
class ReceiptItemMappingResult:
    receipt_item: ReceiptItem
    suggestion: ReceiptItemMappingSuggestion


def normalize_mapping_text(value: str) -> str:
    normalized = value.lower().replace("ё", "е")
    normalized = _NORMALIZE_RE.sub(" ", normalized)
    return _SPACE_RE.sub(" ", normalized).strip()


def map_receipt_details_to_items(
    receipt: Receipt,
    provider_details: FiscalReceiptDetails,
    *,
    replace_existing: bool = True,
) -> list[ReceiptItemMappingResult]:
    return map_receipt_items(
        receipt=receipt,
        items=provider_details.items,
        replace_existing=replace_existing,
    )


def map_receipt_items(
    *,
    receipt: Receipt,
    items: Iterable[ReceiptLineItem],
    replace_existing: bool = True,
) -> list[ReceiptItemMappingResult]:
    item_list = list(items)

    with transaction.atomic():
        if replace_existing:
            receipt.items.all().delete()

        results: list[ReceiptItemMappingResult] = []
        for index, provider_item in enumerate(item_list, start=1):
            suggestion = suggest_category_for_receipt_item(
                user=receipt.user,
                item_name=provider_item.name,
                receipt=receipt,
            )
            receipt_item = ReceiptItem.objects.create(
                receipt=receipt,
                line_number=index,
                name=provider_item.name.strip() or "Позиция чека",
                quantity=_quantize_quantity(provider_item.quantity),
                price=_quantize_money(provider_item.price),
                amount=_quantize_money(provider_item.amount),
                suggested_category=suggestion.category,
                mapping_confidence=suggestion.confidence,
                mapping_reason=suggestion.reason,
                provider_payload=dict(provider_item.raw),
            )
            results.append(
                ReceiptItemMappingResult(
                    receipt_item=receipt_item,
                    suggestion=suggestion,
                )
            )

    return results


def refresh_receipt_item_mappings(receipt: Receipt) -> list[ReceiptItemMappingResult]:
    results: list[ReceiptItemMappingResult] = []
    for receipt_item in receipt.items.select_related("suggested_category").order_by("line_number"):
        suggestion = suggest_category_for_receipt_item(
            user=receipt.user,
            item_name=receipt_item.name,
            receipt=receipt,
        )
        receipt_item.suggested_category = suggestion.category
        receipt_item.mapping_confidence = suggestion.confidence
        receipt_item.mapping_reason = suggestion.reason
        receipt_item.save(
            update_fields=[
                "suggested_category",
                "mapping_confidence",
                "mapping_reason",
                "updated_at",
            ]
        )
        results.append(ReceiptItemMappingResult(receipt_item=receipt_item, suggestion=suggestion))
    return results


def suggest_category_for_receipt_item(
    *,
    user,
    item_name: str,
    receipt: Receipt | None = None,
) -> ReceiptItemMappingSuggestion:
    normalized_item = normalize_mapping_text(" ".join([item_name or "", receipt.store_name if receipt else ""]))
    if not normalized_item:
        return _empty_suggestion("empty_item_name")

    categories = list(
        Category.objects.filter(
            user=user,
            type=TransactionType.EXPENSE,
            is_active=True,
            is_archived=False,
        ).order_by("is_favorite", "sort_order", "name")
    )

    if not categories:
        return _empty_suggestion("no_expense_categories")

    name_match = _find_category_name_match(categories, normalized_item)
    if name_match is not None:
        category, matched_text = name_match
        return ReceiptItemMappingSuggestion(
            category=category,
            confidence=Decimal("0.90"),
            reason=f"category_name_match:{matched_text}",
            matched_keyword=matched_text,
        )

    keyword_match = _find_keyword_match(categories, normalized_item)
    if keyword_match is not None:
        category, keyword = keyword_match
        return ReceiptItemMappingSuggestion(
            category=category,
            confidence=Decimal("0.85"),
            reason=f"keyword_match:{keyword}",
            matched_keyword=keyword,
        )

    return _empty_suggestion("no_match")


def _find_category_name_match(
    categories: list[Category],
    normalized_item: str,
) -> tuple[Category, str] | None:
    for category in categories:
        normalized_category = normalize_mapping_text(category.name)
        if not normalized_category:
            continue

        if _contains_phrase(normalized_item, normalized_category):
            return category, normalized_category

        category_tokens = set(normalized_category.split())
        if category_tokens and category_tokens.issubset(set(normalized_item.split())):
            return category, normalized_category

    return None


def _find_keyword_match(
    categories: list[Category],
    normalized_item: str,
) -> tuple[Category, str] | None:
    category_by_alias: dict[str, Category] = {}
    for category in categories:
        normalized_category = normalize_mapping_text(category.name)
        category_by_alias[normalized_category] = category

    for group in CATEGORY_KEYWORD_GROUPS:
        category = _category_for_group_aliases(category_by_alias, group["aliases"])
        if category is None:
            continue
        for keyword in group["keywords"]:
            normalized_keyword = normalize_mapping_text(keyword)
            if _contains_phrase(normalized_item, normalized_keyword):
                return category, normalized_keyword
    return None


def _category_for_group_aliases(
    category_by_alias: dict[str, Category],
    aliases: tuple[str, ...],
) -> Category | None:
    normalized_aliases = [normalize_mapping_text(alias) for alias in aliases]
    for alias in normalized_aliases:
        if alias in category_by_alias:
            return category_by_alias[alias]

    for category_name, category in category_by_alias.items():
        for alias in normalized_aliases:
            if category_name and (category_name in alias or alias in category_name):
                return category
    return None


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    return f" {phrase} " in f" {text} "


def _empty_suggestion(reason: str) -> ReceiptItemMappingSuggestion:
    return ReceiptItemMappingSuggestion(
        category=None,
        confidence=Decimal("0.00"),
        reason=reason,
    )


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _quantize_quantity(value: Decimal) -> Decimal:
    return Decimal(value).quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)
