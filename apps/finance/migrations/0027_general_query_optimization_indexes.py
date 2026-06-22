# Generated manually for general DB and query optimization.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0026_receipt_query_optimization_indexes"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "type", "operation_date", "account"],
                name="idx_tx_dash_type_date_acct",
            ),
        ),
        migrations.AddIndex(
            model_name="budget",
            index=models.Index(
                fields=["user", "-period_start", "category"],
                name="idx_budget_user_sort_cat",
            ),
        ),
        migrations.AddIndex(
            model_name="goal",
            index=models.Index(
                fields=["user", "status", "deadline", "name"],
                name="idx_goal_status_deadline_name",
            ),
        ),
        migrations.AddIndex(
            model_name="plannedtransaction",
            index=models.Index(
                fields=["user", "account", "planned_date", "status"],
                name="idx_ptx_cal_account_date",
            ),
        ),
    ]
