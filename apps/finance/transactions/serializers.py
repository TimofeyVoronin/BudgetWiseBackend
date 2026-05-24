from decimal import Decimal, ROUND_HALF_UP

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.currencies.services import validate_user_currency_available
from apps.finance.models import (
    Account,
    Category,
    Tag,
    Transaction,
    TransactionLineItem,
    TransactionType,
)
from apps.finance.tags.services import get_accessible_tags


class TransactionTagSerializer(serializers.ModelSerializer):
    groupId = serializers.IntegerField(source="group_id", read_only=True, allow_null=True)
    groupName = serializers.SerializerMethodField(read_only=True)
    isVisible = serializers.BooleanField(source="is_visible", read_only=True)

    class Meta:
        model = Tag
        fields = [
            "id",
            "name",
            "groupId",
            "groupName",
            "color",
            "icon",
            "isVisible",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_groupName(self, obj: Tag) -> str:
        return obj.group.name if obj.group_id else "Без группы"


class TransactionLineItemSerializer(serializers.ModelSerializer):
    qty = serializers.DecimalField(
        source="quantity",
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    unit_price_rub = serializers.DecimalField(
        source="unit_price",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )
    sum_rub = serializers.DecimalField(
        source="amount",
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = TransactionLineItem
        fields = [
            "id",
            "name",
            "qty",
            "unit_price_rub",
            "sum_rub",
        ]
        read_only_fields = ["id"]

    def to_internal_value(self, data):
        mutable_data = data.copy()
        alias_map = {
            "quantity": "qty",
            "unitPriceRub": "unit_price_rub",
            "unit_price": "unit_price_rub",
            "price": "unit_price_rub",
            "sumRub": "sum_rub",
            "sum": "sum_rub",
            "amount": "sum_rub",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        return super().to_internal_value(mutable_data)

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Название позиции не может быть пустым.")
        return value

    def validate(self, attrs):
        quantity = attrs.get("quantity")
        unit_price = attrs.get("unit_price")
        amount = attrs.get("amount")

        if quantity is not None and unit_price is not None and amount is not None:
            calculated_amount = (quantity * unit_price).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if calculated_amount != amount:
                # Не блокируем создание, потому что скидки, округления и весовые товары
                # могут давать расхождение между qty * price и итоговой суммой строки.
                pass

        return attrs


class TransactionSerializer(serializers.ModelSerializer):
    date = serializers.DateField(
        source="operation_date",
        read_only=True,
    )
    kind = serializers.CharField(
        source="type",
        read_only=True,
    )
    amount_abs = serializers.SerializerMethodField(read_only=True)
    signed_amount = serializers.SerializerMethodField(read_only=True)
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    category_icon = serializers.CharField(
        source="category.icon",
        read_only=True,
    )
    category_color = serializers.CharField(
        source="category.color",
        read_only=True,
    )
    account_name = serializers.CharField(
        source="account.name",
        read_only=True,
    )
    account_currency = serializers.CharField(
        source="account.currency",
        read_only=True,
    )
    tagIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    tags = TransactionTagSerializer(many=True, read_only=True)
    line_items = TransactionLineItemSerializer(many=True, required=False)
    receiptId = serializers.IntegerField(source="receipt_id", read_only=True, allow_null=True)
    receiptItemId = serializers.IntegerField(source="receipt_item_id", read_only=True, allow_null=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "account_name",
            "account_currency",
            "category",
            "category_name",
            "category_icon",
            "category_color",
            "type",
            "kind",
            "amount",
            "amount_abs",
            "signed_amount",
            "description",
            "operation_date",
            "date",
            "created_at",
            "updated_at",
            "tagIds",
            "tags",
            "line_items",
            "receiptId",
            "receiptItemId",
        ]
        read_only_fields = [
            "id",
            "account_name",
            "account_currency",
            "category_name",
            "category_icon",
            "category_color",
            "kind",
            "amount_abs",
            "signed_amount",
            "date",
            "created_at",
            "updated_at",
            "tags",
            "receiptId",
            "receiptItemId",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()

        alias_map = {
            "tag_ids": "tagIds",
            "tags": "tagIds",
            "lineItems": "line_items",
        }

        for alias, field_name in alias_map.items():
            if alias in mutable_data and field_name not in mutable_data:
                mutable_data[field_name] = mutable_data[alias]

        tag_ids = mutable_data.get("tagIds")

        if isinstance(tag_ids, str):
            mutable_data["tagIds"] = [
                item.strip()
                for item in tag_ids.split(",")
                if item.strip()
            ]

        return super().to_internal_value(mutable_data)

    def _validate_tag_ids(self, tag_ids: list[int]) -> list[Tag]:
        request = self.context.get("request")

        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError(
                {
                    "tagIds": "Пользователь должен быть авторизован для выбора тегов."
                }
            )

        unique_tag_ids = list(dict.fromkeys(tag_ids))

        if not unique_tag_ids:
            return []

        tags_queryset = (
            get_accessible_tags(request.user)
            .filter(pk__in=unique_tag_ids, is_visible=True)
            .order_by("name", "id")
        )
        tags_by_id = {tag.pk: tag for tag in tags_queryset}
        missing_tag_ids = [tag_id for tag_id in unique_tag_ids if tag_id not in tags_by_id]

        if missing_tag_ids:
            raise serializers.ValidationError(
                {
                    "tagIds": [
                        (
                            "Недоступные, скрытые или несуществующие теги: "
                            + ", ".join(str(tag_id) for tag_id in missing_tag_ids)
                            + "."
                        )
                    ]
                }
            )

        return [tags_by_id[tag_id] for tag_id in unique_tag_ids]

    @extend_schema_field(OpenApiTypes.STR)
    def get_amount_abs(self, obj) -> str:
        return str(abs(obj.amount).quantize(Decimal("0.01")))

    @extend_schema_field(OpenApiTypes.STR)
    def get_signed_amount(self, obj) -> str:
        amount = abs(obj.amount)

        if obj.type == TransactionType.EXPENSE:
            amount = -amount

        return str(amount.quantize(Decimal("0.01")))

    def validate_account(self, account: Account) -> Account:
        request = self.context.get("request")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "Счёт должен принадлежать текущему пользователю."
            )

        return account

    def validate_category(self, category: Category) -> Category:
        request = self.context.get("request")

        if request and category.user_id != request.user.id:
            raise serializers.ValidationError(
                "Категория должна принадлежать текущему пользователю."
            )

        return category

    def validate(self, attrs):
        request = self.context.get("request")
        tag_ids = attrs.pop("tagIds", None)
        self._validated_tags = None
        self._line_items_data_marker = serializers.empty
        self._line_items_data = []

        if "line_items" in attrs:
            self._line_items_data_marker = attrs.pop("line_items")
            self._line_items_data = list(self._line_items_data_marker or [])

        if tag_ids is not None:
            self._validated_tags = self._validate_tag_ids(tag_ids)

        account = attrs.get("account", getattr(self.instance, "account", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        transaction_type = attrs.get("type", getattr(self.instance, "type", None))

        should_validate_account_status = (
            not self.instance or "account" in attrs
        )

        if request and should_validate_account_status and account:
            validate_user_currency_available(
                request.user,
                account.currency,
                field_name="account",
                require_visible=True,
            )

        if should_validate_account_status and account and not account.is_active:
            raise serializers.ValidationError(
                {
                    "account": "Нельзя использовать неактивный счёт."
                }
            )

        if should_validate_account_status and account and account.is_archived:
            raise serializers.ValidationError(
                {
                    "account": "Нельзя использовать архивный счёт."
                }
            )

        should_validate_category_status = (
            not self.instance or "category" in attrs
        )

        if should_validate_category_status and category and not category.is_active:
            raise serializers.ValidationError(
                {
                    "category": "Нельзя использовать неактивную категорию."
                }
            )

        if should_validate_category_status and category and category.is_archived:
            raise serializers.ValidationError(
                {
                    "category": "Нельзя использовать архивную категорию."
                }
            )

        if category and transaction_type and category.type != transaction_type:
            raise serializers.ValidationError(
                {
                    "category": "Тип категории должен совпадать с типом операции."
                }
            )

        if account and category and account.user_id != category.user_id:
            raise serializers.ValidationError(
                {
                    "category": "Счёт и категория должны принадлежать одному пользователю."
                }
            )

        self._validate_line_items_total(attrs)

        return attrs

    def _validate_line_items_total(self, attrs) -> None:
        if self._line_items_data_marker is serializers.empty:
            return

        if not self._line_items_data:
            return

        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if amount is None:
            return

        line_items_total = sum(
            item["amount"]
            for item in self._line_items_data
        ).quantize(Decimal("0.01"))
        transaction_amount = Decimal(amount).quantize(Decimal("0.01"))

        if line_items_total != transaction_amount:
            raise serializers.ValidationError(
                {
                    "line_items": (
                        "Сумма позиций должна совпадать с суммой операции. "
                        f"Сейчас по позициям: {line_items_total}, сумма операции: {transaction_amount}."
                    )
                }
            )

    def create(self, validated_data):
        request = self.context["request"]
        tags = getattr(self, "_validated_tags", None)

        validated_data["user"] = request.user
        transaction = super().create(validated_data)

        if tags is not None:
            transaction.tags.set(tags)

        self._replace_line_items_if_provided(transaction)

        return transaction

    def update(self, instance, validated_data):
        tags = getattr(self, "_validated_tags", None)
        transaction = super().update(instance, validated_data)

        if tags is not None:
            transaction.tags.set(tags)

        self._replace_line_items_if_provided(transaction)

        return transaction

    def _replace_line_items_if_provided(self, transaction: Transaction) -> None:
        if getattr(self, "_line_items_data_marker", serializers.empty) is serializers.empty:
            return

        transaction.line_items.all().delete()
        line_items = [
            TransactionLineItem(
                transaction=transaction,
                line_number=index,
                name=item["name"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                amount=item["amount"],
            )
            for index, item in enumerate(self._line_items_data, start=1)
        ]

        if line_items:
            TransactionLineItem.objects.bulk_create(line_items)
