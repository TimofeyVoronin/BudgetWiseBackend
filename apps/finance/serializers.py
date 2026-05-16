import re

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.finance.models import (
    Account,
    Category,
    Transaction,
    TransactionType,
)


MAX_CATEGORY_SUGGEST_DESCRIPTION_LENGTH = 300
MAX_CATEGORY_SUGGESTIONS_LIMIT = 10


CATEGORY_SUGGESTION_RULES = {
    TransactionType.EXPENSE: [
        (
            (
                "продукт",
                "супермаркет",
                "магазин",
                "пятероч",
                "пятёроч",
                "магнит",
                "лента",
                "ашан",
                "перекрест",
                "перекрёст",
                "metro",
                "grocery",
                "supermarket",
            ),
            (
                "продукт",
                "еда",
                "питани",
                "супермаркет",
                "магазин",
                "food",
                "grocery",
            ),
            0.92,
        ),
        (
            (
                "кафе",
                "ресторан",
                "кофе",
                "кофейня",
                "доставка",
                "пицца",
                "суши",
                "бургер",
                "restaurant",
                "cafe",
                "coffee",
                "delivery",
            ),
            (
                "кафе",
                "ресторан",
                "кофе",
                "доставк",
                "еда",
                "food",
                "restaurant",
                "cafe",
            ),
            0.9,
        ),
        (
            (
                "такси",
                "автобус",
                "метро",
                "транспорт",
                "проезд",
                "билет",
                "uber",
                "taxi",
                "bus",
                "metro",
                "transport",
            ),
            (
                "транспорт",
                "такси",
                "проезд",
                "travel",
                "transport",
                "taxi",
            ),
            0.9,
        ),
        (
            (
                "бензин",
                "топливо",
                "азс",
                "заправка",
                "газпромнефть",
                "лукойл",
                "fuel",
                "gas",
                "petrol",
            ),
            (
                "топлив",
                "бензин",
                "авто",
                "машин",
                "транспорт",
                "fuel",
                "car",
            ),
            0.9,
        ),
        (
            (
                "квартира",
                "аренда",
                "жкх",
                "коммунал",
                "электрич",
                "вода",
                "интернет",
                "rent",
                "utility",
                "utilities",
                "internet",
            ),
            (
                "жиль",
                "квартир",
                "аренд",
                "дом",
                "коммунал",
                "интернет",
                "housing",
                "rent",
                "utilities",
            ),
            0.88,
        ),
        (
            (
                "аптека",
                "лекар",
                "медицин",
                "врач",
                "клиника",
                "pharmacy",
                "medicine",
                "clinic",
                "doctor",
            ),
            (
                "здоров",
                "медицин",
                "аптек",
                "лекар",
                "health",
                "medicine",
                "pharmacy",
            ),
            0.88,
        ),
        (
            (
                "спорт",
                "зал",
                "фитнес",
                "трениров",
                "gym",
                "fitness",
                "sport",
            ),
            (
                "спорт",
                "фитнес",
                "зал",
                "развлеч",
                "gym",
                "fitness",
            ),
            0.84,
        ),
        (
            (
                "кино",
                "театр",
                "игра",
                "подписка",
                "netflix",
                "spotify",
                "entertainment",
                "subscription",
            ),
            (
                "развлеч",
                "подписк",
                "кино",
                "игр",
                "entertainment",
                "subscription",
            ),
            0.84,
        ),
        (
            (
                "одежда",
                "обувь",
                "маркетплейс",
                "wildberries",
                "ozon",
                "wb",
                "clothes",
                "shoes",
                "marketplace",
            ),
            (
                "одеж",
                "обув",
                "покупк",
                "маркет",
                "shopping",
                "clothes",
            ),
            0.84,
        ),
    ],
    TransactionType.INCOME: [
        (
            (
                "зарплата",
                "зп",
                "аванс",
                "оклад",
                "salary",
                "payroll",
                "wage",
            ),
            (
                "зарплат",
                "работ",
                "доход",
                "salary",
                "payroll",
            ),
            0.94,
        ),
        (
            (
                "фриланс",
                "заказ",
                "проект",
                "подработка",
                "freelance",
                "project",
                "side job",
            ),
            (
                "фриланс",
                "заказ",
                "проект",
                "подработ",
                "доход",
                "freelance",
            ),
            0.9,
        ),
        (
            (
                "подарок",
                "перевод",
                "возврат",
                "кэшбэк",
                "cashback",
                "refund",
                "gift",
                "transfer",
            ),
            (
                "подар",
                "перевод",
                "возврат",
                "кэшбэк",
                "cashback",
                "refund",
                "gift",
            ),
            0.86,
        ),
        (
            (
                "процент",
                "вклад",
                "дивиденд",
                "инвест",
                "interest",
                "deposit",
                "dividend",
                "investment",
            ),
            (
                "инвест",
                "дивиденд",
                "процент",
                "вклад",
                "investment",
                "dividend",
            ),
            0.86,
        ),
    ],
}


class CategorySerializer(serializers.ModelSerializer):
    children_count = serializers.SerializerMethodField(read_only=True)
    budgets_count = serializers.SerializerMethodField(read_only=True)
    active_budgets_count = serializers.SerializerMethodField(read_only=True)
    is_available_for_budget = serializers.SerializerMethodField(read_only=True)

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
            "budgets_count",
            "active_budgets_count",
            "is_available_for_budget",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "children_count",
            "budgets_count",
            "active_budgets_count",
            "is_available_for_budget",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(OpenApiTypes.INT)
    def get_children_count(self, obj) -> int:
        return obj.children.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_budgets_count(self, obj) -> int:
        annotated_value = getattr(obj, "budget_count", None)

        if annotated_value is not None:
            return annotated_value

        return obj.budgets.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_active_budgets_count(self, obj) -> int:
        annotated_value = getattr(obj, "active_budget_count", None)

        if annotated_value is not None:
            return annotated_value

        return obj.budgets.filter(is_active=True).count()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_available_for_budget(self, obj) -> bool:
        return (
            obj.type == TransactionType.EXPENSE
            and obj.is_active
            and not obj.is_archived
        )

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


class CategoryFavoriteSerializer(serializers.Serializer):
    favorite = serializers.BooleanField(write_only=True)

    id = serializers.IntegerField(read_only=True)
    is_favorite = serializers.BooleanField(read_only=True)
    detail = serializers.CharField(read_only=True)

    def update(self, instance: Category, validated_data):
        instance.is_favorite = validated_data["favorite"]
        instance.save(update_fields=["is_favorite", "updated_at"])
        return instance

    def create(self, validated_data):
        raise NotImplementedError("CategoryFavoriteSerializer does not create objects.")

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "is_favorite": instance.is_favorite,
            "detail": (
                "Категория добавлена в избранное."
                if instance.is_favorite
                else "Категория удалена из избранного."
            ),
        }


class CategoryArchiveSerializer(serializers.Serializer):
    archived = serializers.BooleanField(
        required=False,
        default=True,
        write_only=True,
    )

    id = serializers.IntegerField(read_only=True)
    is_archived = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    budgets_count = serializers.IntegerField(read_only=True)
    active_budgets_count = serializers.IntegerField(read_only=True)
    detail = serializers.CharField(read_only=True)

    def update(self, instance: Category, validated_data):
        archived = validated_data.get("archived", True)

        instance.is_archived = archived
        instance.is_active = not archived
        instance.save(update_fields=["is_archived", "is_active", "updated_at"])

        return instance

    def create(self, validated_data):
        raise NotImplementedError("CategoryArchiveSerializer does not create objects.")

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "is_archived": instance.is_archived,
            "is_active": instance.is_active,
            "budgets_count": instance.budgets.count(),
            "active_budgets_count": instance.budgets.filter(is_active=True).count(),
            "detail": (
                "Категория отправлена в архив."
                if instance.is_archived
                else "Категория восстановлена из архива."
            ),
        }


class CategoryReorderItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    parent = serializers.IntegerField(required=False, allow_null=True)
    parentId = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    position = serializers.IntegerField(required=False, min_value=0, write_only=True)

    def validate(self, attrs):
        if "parent" not in attrs and "parentId" in attrs:
            attrs["parent"] = attrs["parentId"]

        if "parent" not in attrs:
            attrs["parent"] = None

        if "sort_order" not in attrs and "position" in attrs:
            attrs["sort_order"] = attrs["position"]

        if "sort_order" not in attrs:
            raise serializers.ValidationError(
                {
                    "sort_order": (
                        "Укажите sort_order или position для новой позиции категории."
                    )
                }
            )

        return attrs


class CategoryReorderSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=TransactionType.values,
        required=False,
        write_only=True,
    )
    kind = serializers.ChoiceField(
        choices=TransactionType.values,
        required=False,
        write_only=True,
    )
    order = CategoryReorderItemSerializer(many=True, write_only=True)

    detail = serializers.CharField(read_only=True)
    updated_count = serializers.IntegerField(read_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            raise serializers.ValidationError(
                {
                    "detail": "Пользователь не авторизован."
                }
            )

        category_type = attrs.get("type") or attrs.get("kind")

        if not category_type:
            raise serializers.ValidationError(
                {
                    "type": "Укажите type или kind для перестановки категорий."
                }
            )

        order_items = attrs.get("order") or []

        if not order_items:
            raise serializers.ValidationError(
                {
                    "order": "Передайте непустой список категорий для перестановки."
                }
            )

        category_ids = [item["id"] for item in order_items]

        if len(category_ids) != len(set(category_ids)):
            raise serializers.ValidationError(
                {
                    "order": "Список категорий содержит повторяющиеся id."
                }
            )

        categories = Category.objects.filter(
            user=user,
            id__in=category_ids,
        )
        categories_by_id = {
            category.id: category
            for category in categories
        }

        if len(categories_by_id) != len(category_ids):
            raise serializers.ValidationError(
                {
                    "order": (
                        "Все категории из order должны принадлежать "
                        "текущему пользователю."
                    )
                }
            )

        wrong_type_ids = [
            category.id
            for category in categories_by_id.values()
            if category.type != category_type
        ]

        if wrong_type_ids:
            raise serializers.ValidationError(
                {
                    "order": (
                        "Все перемещаемые категории должны иметь тип "
                        f"{category_type}."
                    )
                }
            )

        parent_ids = {
            item["parent"]
            for item in order_items
            if item.get("parent") is not None
        }

        all_type_categories = Category.objects.filter(
            user=user,
            type=category_type,
        )
        parent_map = {
            category.id: category.parent_id
            for category in all_type_categories
        }

        missing_parent_ids = [
            parent_id
            for parent_id in parent_ids
            if parent_id not in parent_map
        ]

        if missing_parent_ids:
            raise serializers.ValidationError(
                {
                    "order": (
                        "Все родительские категории должны принадлежать "
                        "текущему пользователю и иметь тот же тип."
                    )
                }
            )

        proposed_parent_map = dict(parent_map)

        for item in order_items:
            category_id = item["id"]
            parent_id = item.get("parent")

            if parent_id == category_id:
                raise serializers.ValidationError(
                    {
                        "order": "Категория не может быть родителем самой себя."
                    }
                )

            proposed_parent_map[category_id] = parent_id

        if self._has_cycles(proposed_parent_map):
            raise serializers.ValidationError(
                {
                    "order": "В иерархии категорий обнаружена циклическая связь."
                }
            )

        attrs["type"] = category_type
        attrs["categories_by_id"] = categories_by_id
        return attrs

    def create(self, validated_data):
        order_items = validated_data["order"]
        categories_by_id = validated_data["categories_by_id"]

        now = timezone.now()
        categories_to_update = []

        with transaction.atomic():
            locked_categories = (
                Category.objects
                .select_for_update()
                .filter(id__in=categories_by_id.keys())
            )
            locked_categories_by_id = {
                category.id: category
                for category in locked_categories
            }

            for item in order_items:
                category = locked_categories_by_id[item["id"]]
                category.parent_id = item.get("parent")
                category.sort_order = item["sort_order"]
                category.updated_at = now
                categories_to_update.append(category)

            Category.objects.bulk_update(
                categories_to_update,
                fields=["parent", "sort_order", "updated_at"],
            )

        return {
            "detail": "Порядок категорий обновлён.",
            "updated_count": len(categories_to_update),
        }

    def update(self, instance, validated_data):
        raise NotImplementedError("CategoryReorderSerializer does not update objects.")

    def _has_cycles(self, parent_map: dict[int, int | None]) -> bool:
        for category_id in parent_map:
            visited = set()
            current_id = category_id

            while current_id is not None:
                if current_id in visited:
                    return True

                visited.add(current_id)
                current_id = parent_map.get(current_id)

        return False


class CategorySuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    category = serializers.IntegerField(read_only=True)
    parent = serializers.IntegerField(read_only=True, allow_null=True)
    name = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    icon = serializers.CharField(read_only=True)
    color = serializers.CharField(read_only=True)
    confidence = serializers.FloatField(read_only=True)
    reason = serializers.CharField(read_only=True)
    matched_keyword = serializers.CharField(read_only=True, allow_null=True)


class CategorySuggestSerializer(serializers.Serializer):
    description = serializers.CharField(
        write_only=True,
        trim_whitespace=True,
        min_length=2,
        max_length=MAX_CATEGORY_SUGGEST_DESCRIPTION_LENGTH,
    )
    type = serializers.ChoiceField(
        choices=TransactionType.values,
        required=False,
        write_only=True,
    )
    kind = serializers.ChoiceField(
        choices=TransactionType.values,
        required=False,
        write_only=True,
    )
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=MAX_CATEGORY_SUGGESTIONS_LIMIT,
        default=3,
        write_only=True,
    )

    suggestions = CategorySuggestionSerializer(many=True, read_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            raise serializers.ValidationError(
                {
                    "detail": "Пользователь не авторизован."
                }
            )

        category_type = attrs.get("type") or attrs.get("kind")

        if not category_type:
            raise serializers.ValidationError(
                {
                    "type": "Укажите type или kind для подбора категории."
                }
            )

        description = attrs.get("description", "").strip()

        if not description:
            raise serializers.ValidationError(
                {
                    "description": "Описание операции не может быть пустым."
                }
            )

        attrs["type"] = category_type
        attrs["description"] = description
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        description = validated_data["description"]
        category_type = validated_data["type"]
        limit = validated_data.get("limit", 3)

        normalized_description = self._normalize_text(description)

        categories = (
            Category.objects
            .filter(
                user=user,
                type=category_type,
                is_active=True,
                is_archived=False,
            )
            .order_by("-is_favorite", "sort_order", "name", "id")
        )

        suggestions = []

        for category in categories:
            suggestion = self._build_suggestion(
                category=category,
                normalized_description=normalized_description,
                category_type=category_type,
            )

            if suggestion is not None:
                suggestions.append(suggestion)

        suggestions.sort(
            key=lambda item: (
                -item["confidence"],
                item["name"].lower(),
                item["id"],
            )
        )

        return {
            "suggestions": suggestions[:limit],
        }

    def update(self, instance, validated_data):
        raise NotImplementedError("CategorySuggestSerializer does not update objects.")

    def _build_suggestion(
        self,
        *,
        category: Category,
        normalized_description: str,
        category_type: str,
    ) -> dict | None:
        normalized_name = self._normalize_text(category.name)
        name_score = self._get_name_match_score(
            normalized_name=normalized_name,
            normalized_description=normalized_description,
        )

        if name_score is not None:
            return self._serialize_suggestion(
                category=category,
                confidence=name_score,
                reason="Найдено совпадение с названием категории.",
                matched_keyword=category.name,
            )

        rule_match = self._find_rule_match(
            category=category,
            normalized_description=normalized_description,
            category_type=category_type,
        )

        if rule_match is None:
            return None

        matched_keyword, confidence = rule_match

        return self._serialize_suggestion(
            category=category,
            confidence=confidence,
            reason=f"Найдено совпадение по ключевому слову: {matched_keyword}.",
            matched_keyword=matched_keyword,
        )

    def _serialize_suggestion(
        self,
        *,
        category: Category,
        confidence: float,
        reason: str,
        matched_keyword: str | None,
    ) -> dict:
        return {
            "id": category.id,
            "category": category.id,
            "parent": category.parent_id,
            "name": category.name,
            "type": category.type,
            "icon": category.icon,
            "color": category.color,
            "confidence": round(confidence, 2),
            "reason": reason,
            "matched_keyword": matched_keyword,
        }

    def _get_name_match_score(
        self,
        *,
        normalized_name: str,
        normalized_description: str,
    ) -> float | None:
        if len(normalized_name) >= 3 and normalized_name in normalized_description:
            return 0.95

        name_tokens = self._tokenize(normalized_name)
        description_tokens = set(self._tokenize(normalized_description))

        for token in name_tokens:
            if token in description_tokens:
                return 0.82

        return None

    def _find_rule_match(
        self,
        *,
        category: Category,
        normalized_description: str,
        category_type: str,
    ) -> tuple[str, float] | None:
        normalized_name = self._normalize_text(category.name)
        rules = CATEGORY_SUGGESTION_RULES.get(category_type, [])

        for keywords, category_markers, confidence in rules:
            matched_keyword = self._find_first_keyword(
                normalized_description,
                keywords,
            )

            if matched_keyword is None:
                continue

            if self._category_matches_markers(normalized_name, category_markers):
                return matched_keyword, confidence

        return None

    def _find_first_keyword(
        self,
        normalized_description: str,
        keywords: tuple[str, ...],
    ) -> str | None:
        for keyword in keywords:
            normalized_keyword = self._normalize_text(keyword)

            if normalized_keyword in normalized_description:
                return keyword

        return None

    def _category_matches_markers(
        self,
        normalized_name: str,
        markers: tuple[str, ...],
    ) -> bool:
        for marker in markers:
            normalized_marker = self._normalize_text(marker)

            if normalized_marker in normalized_name:
                return True

        return False

    def _normalize_text(self, value: str) -> str:
        normalized_value = value.lower().replace("ё", "е")
        normalized_value = re.sub(r"\s+", " ", normalized_value)
        return normalized_value.strip()

    def _tokenize(self, value: str) -> list[str]:
        tokens = re.split(r"[^0-9a-zа-я]+", value.lower().replace("ё", "е"))

        return [
            token
            for token in tokens
            if len(token) >= 3
        ]


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    budgets_count = serializers.SerializerMethodField(read_only=True)
    active_budgets_count = serializers.SerializerMethodField(read_only=True)
    is_available_for_budget = serializers.SerializerMethodField(read_only=True)

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
            "budgets_count",
            "active_budgets_count",
            "is_available_for_budget",
            "children",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(OpenApiTypes.INT)
    def get_budgets_count(self, obj) -> int:
        annotated_value = getattr(obj, "budget_count", None)

        if annotated_value is not None:
            return annotated_value

        return obj.budgets.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_active_budgets_count(self, obj) -> int:
        annotated_value = getattr(obj, "active_budget_count", None)

        if annotated_value is not None:
            return annotated_value

        return obj.budgets.filter(is_active=True).count()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_available_for_budget(self, obj) -> bool:
        return (
            obj.type == TransactionType.EXPENSE
            and obj.is_active
            and not obj.is_archived
        )

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_children(self, obj):
        request = self.context.get("request")
        queryset = obj.children.all().order_by("sort_order", "name", "id")

        if request:
            is_active = self._get_bool_query_param(request, "is_active")
            is_archived = self._get_bool_query_param(request, "is_archived")
            is_favorite = self._get_bool_query_param(request, "is_favorite")

            if is_active is not None:
                queryset = queryset.filter(is_active=is_active)

            if is_archived is not None:
                queryset = queryset.filter(is_archived=is_archived)

            if is_favorite is not None:
                queryset = queryset.filter(is_favorite=is_favorite)

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