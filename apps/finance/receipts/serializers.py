from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.finance.currencies.money import build_money_payload
from apps.finance.models import Account, Category, Receipt, ReceiptItem, Transaction
from apps.finance.receipts.transactions import (
    RECEIPT_TRANSACTION_MODE_BY_ITEMS,
    RECEIPT_TRANSACTION_MODE_SINGLE,
    ReceiptItemTransactionInput,
)
from apps.finance.transactions.serializers import TransactionSerializer


RECEIPT_SOURCE_CURRENCY = "RUB"


class ReceiptTransactionItemInputSerializer(serializers.Serializer):
    receiptItemId = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        help_text=(
            "ID уже сохранённой позиции чека. Если не передан, backend создаст "
            "позицию вручную по name, quantity, price и amount."
        ),
    )
    categoryId = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        help_text=(
            "ID категории для позиции. Если не передан для существующей позиции, backend попробует использовать "
            "предложенную категорию позиции чека. Для ручной позиции категория обязательна."
        ),
    )
    name = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=255,
        help_text="Название ручной позиции чека, если receiptItemId не передан.",
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        required=False,
        help_text="Количество ручной позиции. По умолчанию 1.000.",
    )
    price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        help_text="Цена ручной позиции. Если не передана, используется amount.",
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        help_text="Сумма ручной позиции. Если не передана, считается как quantity × price.",
    )

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if "receipt_item_id" in mutable_data and "receiptItemId" not in mutable_data:
            mutable_data["receiptItemId"] = mutable_data["receipt_item_id"]
        if "category_id" in mutable_data and "categoryId" not in mutable_data:
            mutable_data["categoryId"] = mutable_data["category_id"]
        return super().to_internal_value(mutable_data)

    def validate(self, attrs):
        receipt_item_id = attrs.get("receiptItemId")
        if receipt_item_id:
            return attrs

        name = attrs.get("name", "").strip()
        amount = attrs.get("amount")
        quantity = attrs.get("quantity")
        price = attrs.get("price")

        if not name:
            raise serializers.ValidationError(
                {"name": "Для ручной позиции нужно указать название."}
            )

        if amount is None:
            if quantity is None or price is None:
                raise serializers.ValidationError(
                    {"amount": "Для ручной позиции нужно передать amount или пару quantity + price."}
                )
            attrs["amount"] = (quantity * price).quantize(Decimal("0.01"))

        if quantity is None:
            attrs["quantity"] = Decimal("1.000")

        if price is None:
            quantity = attrs["quantity"]
            attrs["price"] = (attrs["amount"] / quantity).quantize(Decimal("0.01"))

        return attrs


class CreateReceiptTransactionsSerializer(serializers.Serializer):
    accountId = serializers.IntegerField(
        min_value=1,
        help_text="ID счёта, к которому будут привязаны созданные операции.",
    )
    mode = serializers.ChoiceField(
        choices=(
            (RECEIPT_TRANSACTION_MODE_SINGLE, "Одна операция на весь чек"),
            (RECEIPT_TRANSACTION_MODE_BY_ITEMS, "Одна операция на каждую позицию"),
        ),
        help_text="Режим создания операций: single или by_items.",
    )
    categoryId = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        help_text="ID категории для режима single.",
    )
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Описание операции в режиме single. Если не передано, backend сформирует описание автоматически.",
    )
    items = ReceiptTransactionItemInputSerializer(
        many=True,
        required=False,
        help_text="Позиции чека для режима by_items.",
    )

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "account_id": "accountId",
            "category_id": "categoryId",
        }
        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]
        return super().to_internal_value(mutable_data)

    def validate(self, attrs):
        mode = attrs.get("mode")
        if mode == RECEIPT_TRANSACTION_MODE_SINGLE and not attrs.get("categoryId"):
            raise serializers.ValidationError(
                {"categoryId": "Для режима single нужно выбрать категорию."}
            )
        if mode == RECEIPT_TRANSACTION_MODE_BY_ITEMS and not attrs.get("items"):
            raise serializers.ValidationError(
                {"items": "Для режима by_items нужно передать позиции чека."}
            )
        return attrs

    def get_account(self, user) -> Account:
        account_id = self.validated_data["accountId"]
        try:
            return Account.objects.get(pk=account_id, user=user)
        except Account.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"accountId": "Счёт не найден."}
            ) from exc

    def get_category(self, user) -> Category | None:
        category_id = self.validated_data.get("categoryId")
        if not category_id:
            return None
        try:
            return Category.objects.get(pk=category_id, user=user)
        except Category.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"categoryId": "Категория не найдена."}
            ) from exc

    def get_item_inputs(self) -> list[ReceiptItemTransactionInput]:
        return [
            ReceiptItemTransactionInput(
                receipt_item_id=item.get("receiptItemId"),
                category_id=item.get("categoryId"),
                name=item.get("name", ""),
                quantity=item.get("quantity"),
                price=item.get("price"),
                amount=item.get("amount"),
            )
            for item in self.validated_data.get("items", [])
        ]


class ReceiptItemBriefSerializer(serializers.ModelSerializer):
    suggestedCategoryId = serializers.IntegerField(source="suggested_category_id", read_only=True, allow_null=True)
    suggestedCategoryName = serializers.CharField(source="suggested_category.name", read_only=True, allow_null=True)
    mappingConfidence = serializers.DecimalField(source="mapping_confidence", max_digits=4, decimal_places=2, read_only=True)
    mappingReason = serializers.CharField(source="mapping_reason", read_only=True)
    sourceCurrency = serializers.SerializerMethodField(read_only=True)
    priceRub = serializers.SerializerMethodField(read_only=True)
    amountRub = serializers.SerializerMethodField(read_only=True)
    priceDisplay = serializers.SerializerMethodField(read_only=True)
    amountDisplay = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "line_number",
            "name",
            "quantity",
            "price",
            "priceRub",
            "priceDisplay",
            "amount",
            "amountRub",
            "amountDisplay",
            "sourceCurrency",
            "suggestedCategoryId",
            "suggestedCategoryName",
            "mappingConfidence",
            "mappingReason",
        ]

    def get_sourceCurrency(self, obj: ReceiptItem) -> str:
        return RECEIPT_SOURCE_CURRENCY

    def get_priceRub(self, obj: ReceiptItem) -> float:
        return self._display_money(obj.price)["amount"]

    def get_amountRub(self, obj: ReceiptItem) -> float:
        return self._display_money(obj.amount)["amount"]

    def get_priceDisplay(self, obj: ReceiptItem) -> dict:
        return self._display_money(obj.price)

    def get_amountDisplay(self, obj: ReceiptItem) -> dict:
        return self._display_money(obj.amount)

    def _display_money(self, value) -> dict:
        converter = self.context.get("currency_converter")

        if converter is None:
            return build_money_payload(value, currency=RECEIPT_SOURCE_CURRENCY)

        return converter.display_amount_payload(
            value,
            source_currency=RECEIPT_SOURCE_CURRENCY,
        )


class ReceiptBriefSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField(read_only=True)
    itemsCount = serializers.SerializerMethodField(read_only=True)
    transactionsCount = serializers.SerializerMethodField(read_only=True)
    sourceCurrency = serializers.SerializerMethodField(read_only=True)
    totalAmountRub = serializers.SerializerMethodField(read_only=True)
    totalAmountDisplay = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "status",
            "store_name",
            "seller_inn",
            "receipt_datetime",
            "total_amount",
            "totalAmountRub",
            "totalAmountDisplay",
            "sourceCurrency",
            "fiscal_drive_number",
            "fiscal_document_number",
            "fiscal_sign",
            "transactionsCount",
            "itemsCount",
            "items",
        ]

    def get_items(self, obj: Receipt) -> list[dict]:
        if not self.context.get("include_receipt_items", True):
            return []

        items = self._get_prefetched_items(obj)
        limit = self.context.get("receipt_items_limit")

        if limit is not None:
            items = items[:limit]

        return ReceiptItemBriefSerializer(items, many=True, context=self.context).data

    def get_itemsCount(self, obj: Receipt) -> int:
        annotated_count = getattr(obj, "items_count", None)
        if annotated_count is not None:
            return annotated_count

        prefetched_cache = getattr(obj, "_prefetched_objects_cache", {})
        if "items" in prefetched_cache:
            return len(prefetched_cache["items"])

        return obj.items.count()

    def get_transactionsCount(self, obj: Receipt) -> int:
        annotated_count = getattr(obj, "transactions_count", None)
        if annotated_count is not None:
            return annotated_count
        return obj.transactions.count()

    def get_sourceCurrency(self, obj: Receipt) -> str:
        return RECEIPT_SOURCE_CURRENCY

    def get_totalAmountRub(self, obj: Receipt) -> float:
        return self._display_money(obj.total_amount)["amount"]

    def get_totalAmountDisplay(self, obj: Receipt) -> dict:
        return self._display_money(obj.total_amount)

    def _display_money(self, value) -> dict:
        converter = self.context.get("currency_converter")

        if converter is None:
            return build_money_payload(value, currency=RECEIPT_SOURCE_CURRENCY)

        return converter.display_amount_payload(
            value,
            source_currency=RECEIPT_SOURCE_CURRENCY,
        )

    def _get_prefetched_items(self, obj: Receipt):
        prefetched_cache = getattr(obj, "_prefetched_objects_cache", {})
        if "items" in prefetched_cache:
            return list(prefetched_cache["items"])

        return list(
            obj.items.select_related("suggested_category")
            .order_by("line_number", "id")
        )


class ReceiptQRImportQuerySerializer(serializers.Serializer):
    qrRaw = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Исходная строка QR-кода чека. Значение нужно передавать URL-encoded.",
    )
    fetchProvider = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Если true, backend попробует получить расширенные данные чека у внешнего провайдера.",
    )
    includeItems = serializers.BooleanField(
        required=False,
        default=True,
        help_text=(
            "Если false, backend не будет встраивать позиции чека в ответ. "
            "Это полезно для чеков с большим количеством строк: позиции можно получить "
            "постранично через /receipts/{id}/items/."
        ),
    )
    itemsLimit = serializers.IntegerField(
        min_value=1,
        max_value=100,
        required=False,
        allow_null=True,
        help_text=(
            "Ограничивает количество встроенных позиций в receipt.items. "
            "Полный список позиций доступен через /receipts/{id}/items/."
        ),
    )

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "qr_raw": "qrRaw",
            "qr": "qrRaw",
            "fetch_provider": "fetchProvider",
            "include_items": "includeItems",
            "items_limit": "itemsLimit",
        }
        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]
        return super().to_internal_value(mutable_data)


class ReceiptProviderErrorBriefSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    fieldErrors = serializers.DictField(read_only=True, required=False)


class ReceiptItemsResponseSerializer(serializers.Serializer):
    receiptId = serializers.IntegerField(read_only=True)
    itemsCount = serializers.IntegerField(read_only=True)
    items = ReceiptItemBriefSerializer(many=True, read_only=True)
    pagination = serializers.DictField(read_only=True, required=False)
    currencyContext = serializers.DictField(read_only=True)


def build_receipt_items_response(
    *,
    receipt: Receipt,
    items: list[ReceiptItem],
    context: dict | None = None,
    pagination: dict | None = None,
) -> dict:
    context = context or {}
    converter = context.get("currency_converter")
    items_count = getattr(receipt, "items_count", None)
    if items_count is None:
        items_count = receipt.items.count()

    response_data = {
        "receiptId": receipt.id,
        "itemsCount": items_count,
        "items": ReceiptItemBriefSerializer(items, many=True, context=context).data,
        "currencyContext": converter.context_payload() if converter is not None else {},
    }

    if pagination is not None:
        response_data["pagination"] = pagination

    return response_data


class ReceiptQRImportResponseSerializer(serializers.Serializer):
    receipt = ReceiptBriefSerializer(read_only=True)
    created = serializers.BooleanField(read_only=True)
    isDuplicate = serializers.BooleanField(read_only=True)
    providerStatus = serializers.ChoiceField(
        choices=(
            ("skipped", "Провайдер не вызывался"),
            ("fetched", "Чек получен от провайдера"),
            ("failed", "Провайдер вернул ошибку"),
        ),
        read_only=True,
    )
    providerError = ReceiptProviderErrorBriefSerializer(read_only=True, allow_null=True)
    currencyContext = serializers.DictField(read_only=True)


def build_receipt_qr_import_response(
    *,
    receipt: Receipt,
    created: bool,
    is_duplicate: bool,
    provider_status: str,
    provider_error: dict | None = None,
    context: dict | None = None,
) -> dict:
    context = context or {}
    converter = context.get("currency_converter")
    return {
        "receipt": ReceiptBriefSerializer(receipt, context=context).data,
        "created": created,
        "isDuplicate": is_duplicate,
        "providerStatus": provider_status,
        "providerError": provider_error,
        "currencyContext": converter.context_payload() if converter is not None else {},
    }


class CreateReceiptTransactionsResponseSerializer(serializers.Serializer):
    receipt = ReceiptBriefSerializer(read_only=True)
    mode = serializers.CharField(read_only=True)
    createdCount = serializers.IntegerField(read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    currencyContext = serializers.DictField(read_only=True)


def build_receipt_transactions_response(
    *,
    receipt: Receipt,
    mode: str,
    transactions: tuple[Transaction, ...],
    context: dict | None = None,
) -> dict:
    context = context or {}
    converter = context.get("currency_converter")
    return {
        "receipt": ReceiptBriefSerializer(receipt, context=context).data,
        "mode": mode,
        "createdCount": len(transactions),
        "transactions": TransactionSerializer(transactions, many=True, context=context).data,
        "currencyContext": converter.context_payload() if converter is not None else {},
    }
