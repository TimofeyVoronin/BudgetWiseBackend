# Generated manually for receipt query optimization.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0025_offline_sync"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(
                fields=["user", "status", "receipt_datetime"],
                name="idx_receipt_user_status_date",
            ),
        ),
        migrations.AddIndex(
            model_name="receipt",
            index=models.Index(
                fields=["user", "receipt_datetime", "status"],
                name="idx_receipt_user_date_status",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(
                fields=["receipt", "line_number"],
                name="idx_receipt_item_receipt_line",
            ),
        ),
        migrations.AddIndex(
            model_name="receiptitem",
            index=models.Index(
                fields=["receipt", "id"],
                name="idx_receipt_item_receipt_id",
            ),
        ),
    ]
