from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.finance.models import Category, Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner
from apps.finance.serializers import (
    CategorySerializer,
    CategoryTreeSerializer,
    TransactionSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = Category.objects.filter(user=self.request.user).order_by("type", "name")

        category_type = self.request.query_params.get("type")
        parent_id = self._get_int_query_param("parent")
        is_active = self._get_bool_query_param("is_active")
        ordering = self.request.query_params.get("ordering")

        if category_type:
            if category_type not in TransactionType.values:
                raise ValidationError(
                    {"type": "Допустимые значения: income, expense."}
                )
            queryset = queryset.filter(type=category_type)

        if parent_id is not None:
            queryset = queryset.filter(parent_id=parent_id)

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if ordering:
            allowed_ordering = {
                "name",
                "-name",
                "type",
                "-type",
                "created_at",
                "-created_at",
            }

            if ordering not in allowed_ordering:
                raise ValidationError(
                    {
                        "ordering": (
                            "Допустимые значения: name, -name, type, -type, "
                            "created_at, -created_at."
                        )
                    }
                )

            queryset = queryset.order_by(ordering)

        return queryset

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        queryset = self.get_queryset().filter(parent__isnull=True).order_by("type", "name")
        serializer = CategoryTreeSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        has_related_data = (
            instance.children.exists()
            or instance.transactions.exists()
            or instance.budgets.exists()
        )

        if has_related_data:
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            return Response(status=status.HTTP_204_NO_CONTENT)

        return super().destroy(request, *args, **kwargs)

    def _get_int_query_param(self, name: str):
        value = self.request.query_params.get(name)

        if value in (None, ""):
            return None

        try:
            return int(value)
        except ValueError as exc:
            raise ValidationError(
                {name: "Параметр должен быть целым числом."}
            ) from exc

    def _get_bool_query_param(self, name: str):
        value = self.request.query_params.get(name)

        if value in (None, ""):
            return None

        if value in ("true", "True", "1"):
            return True

        if value in ("false", "False", "0"):
            return False

        raise ValidationError(
            {name: "Параметр должен быть boolean: true или false."}
        )


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, IsObjectOwner]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = (
            Transaction.objects.filter(user=self.request.user)
            .select_related("account", "category")
            .order_by("-operation_date", "-created_at")
        )

        account_id = self._get_int_query_param("account")
        category_id = self._get_int_query_param("category")
        transaction_type = self.request.query_params.get("type")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        ordering = self.request.query_params.get("ordering")

        if account_id is not None:
            queryset = queryset.filter(account_id=account_id)

        if category_id is not None:
            queryset = queryset.filter(category_id=category_id)

        if transaction_type:
            if transaction_type not in TransactionType.values:
                raise ValidationError(
                    {"type": "Допустимые значения: income, expense."}
                )
            queryset = queryset.filter(type=transaction_type)

        if date_from:
            parsed_date_from = parse_date(date_from)
            if parsed_date_from is None:
                raise ValidationError(
                    {"date_from": "Дата должна быть в формате YYYY-MM-DD."}
                )
            queryset = queryset.filter(operation_date__gte=parsed_date_from)

        if date_to:
            parsed_date_to = parse_date(date_to)
            if parsed_date_to is None:
                raise ValidationError(
                    {"date_to": "Дата должна быть в формате YYYY-MM-DD."}
                )
            queryset = queryset.filter(operation_date__lte=parsed_date_to)

        if ordering:
            allowed_ordering = {
                "operation_date",
                "-operation_date",
                "amount",
                "-amount",
                "created_at",
                "-created_at",
            }

            if ordering not in allowed_ordering:
                raise ValidationError(
                    {
                        "ordering": (
                            "Допустимые значения: operation_date, "
                            "-operation_date, amount, -amount, "
                            "created_at, -created_at."
                        )
                    }
                )

            queryset = queryset.order_by(ordering)

        return queryset

    def _get_int_query_param(self, name: str):
        value = self.request.query_params.get(name)

        if value in (None, ""):
            return None

        try:
            return int(value)
        except ValueError as exc:
            raise ValidationError(
                {name: "Параметр должен быть целым числом."}
            ) from exc