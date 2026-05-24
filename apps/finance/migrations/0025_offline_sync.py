# Generated for BUD-1124 offline sync API.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("finance", "0024_transaction_line_items"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfflineSyncOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("client_id", models.CharField(max_length=100, verbose_name="ID клиента")),
                ("device_id", models.CharField(max_length=150, verbose_name="ID устройства")),
                ("client_mutation_id", models.CharField(max_length=150, verbose_name="ID клиентской мутации")),
                ("resource", models.CharField(max_length=60, verbose_name="Ресурс")),
                ("action", models.CharField(choices=[("create", "Создание"), ("update", "Обновление"), ("delete", "Удаление")], max_length=20, verbose_name="Действие")),
                ("status", models.CharField(choices=[("applied", "Применена"), ("duplicate", "Дубликат"), ("failed", "Ошибка"), ("conflict", "Конфликт"), ("skipped", "Пропущена")], default="applied", max_length=20, verbose_name="Статус")),
                ("object_id", models.PositiveBigIntegerField(blank=True, null=True, verbose_name="ID объекта на сервере")),
                ("request_hash", models.CharField(blank=True, max_length=64, verbose_name="Хеш запроса")),
                ("response_data", models.JSONField(blank=True, default=dict, verbose_name="Сохранённый ответ")),
                ("error_data", models.JSONField(blank=True, default=dict, verbose_name="Данные ошибки")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offline_sync_operations", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Операция оффлайн-синхронизации",
                "verbose_name_plural": "Операции оффлайн-синхронизации",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="OfflineSyncTombstone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("resource", models.CharField(max_length=60, verbose_name="Ресурс")),
                ("object_id", models.PositiveBigIntegerField(verbose_name="ID удалённого объекта")),
                ("deleted_at", models.DateTimeField(default=django.utils.timezone.now, verbose_name="Дата удаления")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offline_sync_tombstones", to=settings.AUTH_USER_MODEL, verbose_name="Пользователь")),
            ],
            options={
                "verbose_name": "Маркер удаления для оффлайн-синхронизации",
                "verbose_name_plural": "Маркеры удаления для оффлайн-синхронизации",
                "ordering": ["-deleted_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="offlinesyncoperation",
            constraint=models.UniqueConstraint(fields=("user", "client_id", "device_id", "client_mutation_id"), name="unique_offline_sync_mutation"),
        ),
        migrations.AddConstraint(
            model_name="offlinesyncoperation",
            constraint=models.CheckConstraint(condition=models.Q(("action__in", ["create", "update", "delete"])), name="offline_sync_action_valid"),
        ),
        migrations.AddConstraint(
            model_name="offlinesyncoperation",
            constraint=models.CheckConstraint(condition=models.Q(("status__in", ["applied", "duplicate", "failed", "conflict", "skipped"])), name="offline_sync_status_valid"),
        ),
        migrations.AddIndex(
            model_name="offlinesyncoperation",
            index=models.Index(fields=["user", "resource"], name="idx_sync_op_user_resource"),
        ),
        migrations.AddIndex(
            model_name="offlinesyncoperation",
            index=models.Index(fields=["user", "status"], name="idx_sync_op_user_status"),
        ),
        migrations.AddIndex(
            model_name="offlinesyncoperation",
            index=models.Index(fields=["user", "client_id", "device_id"], name="idx_sync_op_client_device"),
        ),
        migrations.AddIndex(
            model_name="offlinesyncoperation",
            index=models.Index(fields=["user", "created_at"], name="idx_sync_op_user_created"),
        ),
        migrations.AddConstraint(
            model_name="offlinesynctombstone",
            constraint=models.UniqueConstraint(fields=("user", "resource", "object_id"), name="unique_offline_sync_tombstone"),
        ),
        migrations.AddIndex(
            model_name="offlinesynctombstone",
            index=models.Index(fields=["user", "resource", "deleted_at"], name="idx_sync_tomb_user_res_date"),
        ),
        migrations.AddIndex(
            model_name="offlinesynctombstone",
            index=models.Index(fields=["user", "deleted_at"], name="idx_sync_tomb_user_date"),
        ),
    ]
