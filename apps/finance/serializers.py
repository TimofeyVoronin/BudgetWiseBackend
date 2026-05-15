from django.db.models import Max
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import (
    Account,
    Category,
    Transaction,
)


class CategorySerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "parent",
            "name",
            "type",
            "icon",
            "color",
            "sort_order",
            "is_favorite",
            "is_archived",
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

    @extend_schema_field(OpenApiTypes.INT)
    def get_children_count(self, obj) -> int:
        return obj.children.count()

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        name = attrs.get("name", getattr(self.instance, "name", None))
        category_type = attrs.get("type", getattr(self.instance, "type", None))

        if user and parent and parent.user_id != user.id:
            raise serializers.ValidationError(
                {
                    "parent": (
                        "Родительская категория должна принадлежать "
                        "текущему пользователю."
                    )
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
                        "type": (
                            "Нельзя изменить тип категории, у которой есть "
                            "дочерние категории."
                        )
                    }
                )

            if self.instance.transactions.exists():
                raise serializers.ValidationError(
                    {
                        "type": (
                            "Нельзя изменить тип категории, которая используется "
                            "в операциях."
                        )
                    }
                )

            if self.instance.budgets.exists():
                raise serializers.ValidationError(
                    {
                        "type": (
                            "Нельзя изменить тип категории, которая используется "
                            "в бюджетах."
                        )
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
        user = request.user

        validated_data["user"] = user

        if "sort_order" not in validated_data:
            validated_data["sort_order"] = self._get_next_sort_order(
                user=user,
                category_type=validated_data["type"],
                parent=validated_data.get("parent"),
            )

        return super().create(validated_data)

    def update(self, instance, validated_data):
        parent_changed = (
            "parent" in validated_data
            and validated_data["parent"] != instance.parent
        )
        type_changed = (
            "type" in validated_data
            and validated_data["type"] != instance.type
        )

        if (parent_changed or type_changed) and "sort_order" not in validated_data:
            validated_data["sort_order"] = self._get_next_sort_order(
                user=instance.user,
                category_type=validated_data.get("type", instance.type),
                parent=validated_data.get("parent", instance.parent),
                exclude_instance=instance,
            )

        return super().update(instance, validated_data)

    def _get_next_sort_order(
        self,
        *,
        user,
        category_type: str,
        parent: Category | None,
        exclude_instance: Category | None = None,
    ) -> int:
        queryset = Category.objects.filter(
            user=user,
            type=category_type,
            parent=parent,
        )

        if exclude_instance is not None:
            queryset = queryset.exclude(pk=exclude_instance.pk)

        max_sort_order = queryset.aggregate(
            max_sort_order=Max("sort_order")
        )["max_sort_order"]

        if max_sort_order is None:
            return 0

        return max_sort_order + 1

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
            "icon",
            "color",
            "sort_order",
            "is_favorite",
            "is_archived",
            "is_active",
            "children",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_children(self, obj):
        request = self.context.get("request")
        queryset = obj.children.all().order_by("sort_order", "name", "id")

        if request:
            is_active = self._get_bool_query_param(request, "is_active")
            is_archived = self._get_bool_query_param(request, "is_archived")

            if is_active is not None:
                queryset = queryset.filter(is_active=is_active)

            if is_archived is not None:
                queryset = queryset.filter(is_archived=is_archived)

        serializer = CategoryTreeSerializer(
            queryset,
            many=True,
            context=self.context,
        )
        return serializer.data

    def _get_bool_query_param(self, request, name: str) -> bool | None:
        value = request.query_params.get(name)

        if value in ("true", "True", "1"):
            return True

        if value in ("false", "False", "0"):
            return False

        return None


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

        if (not self.instance or "account" in attrs) and account and not account.is_active:
            raise serializers.ValidationError(
                {
                    "account": "Нельзя использовать неактивный счёт."
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

        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["user"] = request.user
        return super().create(validated_data)