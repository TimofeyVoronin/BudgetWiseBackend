from rest_framework import serializers

from apps.finance.transaction_serializers import TransactionSerializer


class DashboardPeriodSerializer(serializers.Serializer):
    type = serializers.CharField(read_only=True)
    date_from = serializers.DateField(read_only=True)
    date_to = serializers.DateField(read_only=True)


class DashboardTotalsSerializer(serializers.Serializer):
    accounts_balance = serializers.CharField(read_only=True)
    income = serializers.CharField(read_only=True)
    expense = serializers.CharField(read_only=True)
    net = serializers.CharField(read_only=True)


class DashboardTopExpenseCategorySerializer(serializers.Serializer):
    category = serializers.IntegerField(read_only=True)
    category_name = serializers.CharField(read_only=True)
    category_icon = serializers.CharField(read_only=True)
    category_color = serializers.CharField(read_only=True)
    total = serializers.CharField(read_only=True)


class DashboardReminderRowSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    subtitle = serializers.CharField(read_only=True)
    dateLabel = serializers.CharField(read_only=True)
    icon = serializers.CharField(read_only=True)
    dateEmphasis = serializers.BooleanField(read_only=True)


class DashboardRemindersCardSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    headerIcon = serializers.CharField(read_only=True)
    rows = DashboardReminderRowSerializer(many=True, read_only=True)
    footerLinkLabel = serializers.CharField(read_only=True)


class DashboardSummarySerializer(serializers.Serializer):
    period = DashboardPeriodSerializer(read_only=True)
    currency = serializers.CharField(read_only=True)
    totals = DashboardTotalsSerializer(read_only=True)
    recent_transactions = TransactionSerializer(many=True, read_only=True)
    top_expense_categories = DashboardTopExpenseCategorySerializer(
        many=True,
        read_only=True,
    )
    reminders = DashboardRemindersCardSerializer(read_only=True)
