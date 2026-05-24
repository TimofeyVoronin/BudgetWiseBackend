from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.finance.models import Account, Category, Receipt, ReceiptItem, Transaction
from apps.finance.receipts.transactions import (
    RECEIPT_TRANSACTION_MODE_BY_ITEMS,
    RECEIPT_TRANSACTION_MODE_SINGLE,
    ReceiptItemTransactionInput,
)
from apps.finance.transactions.serializers import TransactionSerializer


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

    class Meta:
        model = ReceiptItem
        fields = [
            "id",
            "line_number",
            "name",
            "quantity",
            "price",
            "amount",
            "suggestedCategoryId",
            "suggestedCategoryName",
            "mappingConfidence",
            "mappingReason",
        ]


class ReceiptBriefSerializer(serializers.ModelSerializer):
    items = ReceiptItemBriefSerializer(many=True, read_only=True)
    transactionsCount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "status",
            "store_name",
            "seller_inn",
            "receipt_datetime",
            "total_amount",
            "fiscal_drive_number",
            "fiscal_document_number",
            "fiscal_sign",
            "transactionsCount",
            "items",
        ]

    def get_transactionsCount(self, obj: Receipt) -> int:
        return obj.transactions.count()


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

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "qr_raw": "qrRaw",
            "qr": "qrRaw",
            "fetch_provider": "fetchProvider",
        }
        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]
        return super().to_internal_value(mutable_data)


class ReceiptProviderErrorBriefSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    fieldErrors = serializers.DictField(read_only=True, required=False)


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


def build_receipt_qr_import_response(
    *,
    receipt: Receipt,
    created: bool,
    is_duplicate: bool,
    provider_status: str,
    provider_error: dict | None = None,
) -> dict:
    return {
        "receipt": ReceiptBriefSerializer(receipt).data,
        "created": created,
        "isDuplicate": is_duplicate,
        "providerStatus": provider_status,
        "providerError": provider_error,
    }


class CreateReceiptTransactionsResponseSerializer(serializers.Serializer):
    receipt = ReceiptBriefSerializer(read_only=True)
    mode = serializers.CharField(read_only=True)
    createdCount = serializers.IntegerField(read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)


def build_receipt_transactions_response(*, receipt: Receipt, mode: str, transactions: tuple[Transaction, ...]) -> dict:
    return {
        "receipt": ReceiptBriefSerializer(receipt).data,
        "mode": mode,
        "createdCount": len(transactions),
        "transactions": TransactionSerializer(transactions, many=True).data,
    }
