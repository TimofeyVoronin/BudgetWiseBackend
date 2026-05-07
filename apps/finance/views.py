from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.finance.models import Transaction, TransactionType
from apps.finance.permissions import IsObjectOwner
from apps.finance.serializers import TransactionSerializer


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