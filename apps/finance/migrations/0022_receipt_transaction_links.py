# Generated for BUD-1044 receipt transactions.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0021_receipt_items"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="receipt",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transactions",
                to="finance.receipt",
                verbose_name="Источник: чек",
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="receipt_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transactions",
                to="finance.receiptitem",
                verbose_name="Источник: позиция чека",
            ),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["user", "receipt"], name="idx_tx_user_receipt"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["receipt_item"], name="idx_tx_receipt_item"),
        ),
    ]
