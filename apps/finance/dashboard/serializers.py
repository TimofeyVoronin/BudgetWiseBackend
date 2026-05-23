from rest_framework import serializers

from apps.finance.transactions.serializers import TransactionSerializer


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


class DashboardPeriodOptionSerializer(serializers.Serializer):
    value = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)


class DashboardCurrencyOptionSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    value = serializers.CharField(read_only=True)


class PeriodCurrencyBarSerializer(serializers.Serializer):
    defaultPeriod = serializers.CharField(read_only=True)
    defaultCurrency = serializers.CharField(read_only=True)
    periodOptions = DashboardPeriodOptionSerializer(many=True, read_only=True)
    currencies = DashboardCurrencyOptionSerializer(many=True, read_only=True)


class BalanceCardSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    headerIcon = serializers.CharField(read_only=True)
    amountRub = serializers.FloatField(read_only=True)
    trendLabel = serializers.CharField(read_only=True)


class AccountsCardRowSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    amountRub = serializers.FloatField(read_only=True)
    icon = serializers.CharField(read_only=True)


class AccountsCardSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    headerIcon = serializers.CharField(read_only=True)
    rows = AccountsCardRowSerializer(many=True, read_only=True)
    footerLinkLabel = serializers.CharField(read_only=True)


class GoalsCardItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    targetRub = serializers.FloatField(read_only=True)
    currentRub = serializers.FloatField(read_only=True)
    percent = serializers.FloatField(read_only=True)


class GoalsCardSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    headerIcon = serializers.CharField(read_only=True)
    goals = GoalsCardItemSerializer(many=True, read_only=True)


class ExpenseDynamicsWeekSerializer(serializers.Serializer):
    label = serializers.CharField(read_only=True)
    income = serializers.IntegerField(read_only=True, min_value=0, max_value=100)
    expenses = serializers.IntegerField(read_only=True, min_value=0, max_value=100)


class ExpenseDynamicsCardSerializer(serializers.Serializer):
    title = serializers.CharField(read_only=True)
    headerIcon = serializers.CharField(read_only=True)
    monthLabel = serializers.CharField(read_only=True)
    legendIncome = serializers.CharField(read_only=True)
    legendExpenses = serializers.CharField(read_only=True)
    yAxisLabels = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )
    weeks = ExpenseDynamicsWeekSerializer(many=True, read_only=True)
