from rest_framework import serializers

from apps.finance.models import (
    Account,
    Category,
    Transaction,
    TransactionType,
)


class CategorySerializer(serializers.ModelSerializer):
    children_count = serializers.IntegerField(
        source="children.count",
        read_only=True,
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "parent",
            "name",
            "type",
            "is_active",
            "children_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "children_count",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        name = attrs.get("name", getattr(self.instance, "name", None))
        category_type = attrs.get("type", getattr(self.instance, "type", None))

        if user and parent and parent.user_id != user.id:
            raise serializers.ValidationError(
                {
                    "parent": "Родительская категория должна принадлежать текущему пользователю."
                }
            )

        if parent and category_type and parent.type != category_type:
            raise serializers.ValidationError(
                {
                    "parent": "Родительская категория должна иметь тот же тип."
                }
            )

        if self.instance and parent and parent.id == self.instance.id:
            raise serializers.ValidationError(
                {
                    "parent": "Категория не может быть родителем самой себя."
                }
            )

        if self.instance and parent and self._has_parent_cycle(self.instance, parent):
            raise serializers.ValidationError(
                {
                    "parent": "В иерархии категорий обнаружена циклическая связь."
                }
            )

        if self.instance and "type" in attrs and attrs["type"] != self.instance.type:
            if self.instance.children.exists():
                raise serializers.ValidationError(
                    {
                        "type": "Нельзя изменить тип категории, у которой есть дочерние категории."
                    }
                )

            if self.instance.transactions.exists():
                raise serializers.ValidationError(
                    {
                        "type": "Нельзя изменить тип категории, которая используется в операциях."
                    }
                )

            if self.instance.budgets.exists():
                raise serializers.ValidationError(
                    {
                        "type": "Нельзя изменить тип категории, которая используется в бюджетах."
                    }
                )

        if user and name and category_type:
            queryset = Category.objects.filter(
                user=user,
                name=name,
                type=category_type,
            )

            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise serializers.ValidationError(
                    {
                        "name": "Категория с таким названием и типом уже существует."
                    }
                )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user
        return super().create(validated_data)

    def _has_parent_cycle(self, instance: Category, parent: Category) -> bool:
        current_parent = parent
        visited_ids = set()

        while current_parent is not None:
            if current_parent.id == instance.id:
                return True

            if current_parent.id in visited_ids:
                return True

            visited_ids.add(current_parent.id)
            current_parent = current_parent.parent

        return False


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "parent",
            "name",
            "type",
            "is_active",
            "children",
            "created_at",
            "updated_at",
        ]

    def get_children(self, obj):
        request = self.context.get("request")
        queryset = obj.children.all().order_by("type", "name")

        if request:
            is_active = request.query_params.get("is_active")

            if is_active in ("true", "True", "1"):
                queryset = queryset.filter(is_active=True)

            if is_active in ("false", "False", "0"):
                queryset = queryset.filter(is_active=False)

        serializer = CategoryTreeSerializer(
            queryset,
            many=True,
            context=self.context,
        )
        return serializer.data


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "category",
            "type",
            "amount",
            "description",
            "operation_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

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
        account = attrs.get("account", getattr(self.instance, "account", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        transaction_type = attrs.get("type", getattr(self.instance, "type", None))

        if category and transaction_type and category.type != transaction_type:
            raise serializers.ValidationError(
                {
                    "category": (
                        "Тип категории должен совпадать с типом операции."
                    )
                }
            )

        if account and category and account.user_id != category.user_id:
            raise serializers.ValidationError(
                {
                    "category": (
                        "Счёт и категория должны принадлежать одному пользователю."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user
        return super().create(validated_data)