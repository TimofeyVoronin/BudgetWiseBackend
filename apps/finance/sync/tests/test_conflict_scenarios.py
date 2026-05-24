from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.finance.models import (
    Account,
    OfflineSyncOperation,
    OfflineSyncOperationStatus,
    OfflineSyncTombstone,
    Transaction,
)
from apps.finance.testing import FinanceAPITestCase


class OfflineSyncConflictScenarioTests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def _push(self, operations):
        return self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": operations,
            },
            format="json",
        )

    def test_simultaneous_transaction_edit_returns_conflict_and_is_logged(self):
        transaction = self.create_transaction(
            amount="100.00",
            description="Исходная версия",
        )
        base_version = transaction.updated_at
        server_version = base_version + timedelta(minutes=5)
        Transaction.objects.filter(pk=transaction.pk).update(
            amount=Decimal("120.00"),
            description="Серверная версия",
            updated_at=server_version,
        )

        response = self._push(
            [
                {
                    "clientMutationId": "conflict-simultaneous-edit",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": transaction.pk,
                    "baseVersion": base_version.isoformat(),
                    "clientUpdatedAt": (server_version + timedelta(minutes=1)).isoformat(),
                    "payload": {
                        "amount": "130.00",
                        "description": "Клиентская версия",
                    },
                }
            ]
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["error"]["code"], "sync_conflict")
        self.assertEqual(result["data"]["clientData"]["description"], "Клиентская версия")
        self.assertEqual(result["data"]["serverData"]["description"], "Серверная версия")
        conflict_fields = {item["field"] for item in result["data"]["conflictFields"]}
        self.assertIn("amount", conflict_fields)
        self.assertIn("description", conflict_fields)

        operation = OfflineSyncOperation.objects.get(client_mutation_id="conflict-simultaneous-edit")
        self.assertEqual(operation.status, OfflineSyncOperationStatus.CONFLICT)
        self.assertEqual(operation.object_id, transaction.pk)
        self.assertEqual(operation.error_data["code"], "sync_conflict")

        log_response = self.client.get(
            "/api/v1/finance/sync/operations/",
            {"status": "conflict", "clientMutationId": "conflict-simultaneous-edit"},
        )
        self.assertEqual(log_response.status_code, 200)
        self.assertEqual(log_response.data["count"], 1)
        self.assertEqual(log_response.data["results"][0]["status"], "conflict")

    def test_delete_with_stale_base_version_returns_conflict_and_keeps_object(self):
        account = Account.objects.create(
            user=self.user,
            name="Счёт с серверным изменением",
            initial_balance=Decimal("0.00"),
            balance=Decimal("0.00"),
            currency="RUB",
        )
        base_version = account.updated_at
        server_version = base_version + timedelta(minutes=3)
        Account.objects.filter(pk=account.pk).update(
            name="Сервер переименовал счёт",
            updated_at=server_version,
        )

        response = self._push(
            [
                {
                    "clientMutationId": "conflict-delete-stale-account",
                    "resource": "accounts",
                    "action": "delete",
                    "serverId": account.pk,
                    "baseVersion": base_version.isoformat(),
                    "clientUpdatedAt": (server_version + timedelta(minutes=1)).isoformat(),
                    "payload": {},
                }
            ]
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["error"]["code"], "sync_conflict")
        self.assertTrue(Account.objects.filter(pk=account.pk).exists())
        self.assertFalse(
            OfflineSyncTombstone.objects.filter(
                user=self.user,
                resource="accounts",
                object_id=account.pk,
            ).exists()
        )

    def test_update_after_server_delete_returns_failed_without_creating_record(self):
        transaction = self.create_transaction(
            amount="70.00",
            description="Удаляемая серверная операция",
        )
        base_version = transaction.updated_at
        deleted_id = transaction.pk
        transaction.delete()
        OfflineSyncTombstone.objects.create(
            user=self.user,
            resource="transactions",
            object_id=deleted_id,
            deleted_at=timezone.now(),
        )

        response = self._push(
            [
                {
                    "clientMutationId": "conflict-update-deleted-transaction",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": deleted_id,
                    "baseVersion": base_version.isoformat(),
                    "payload": {"description": "Клиент редактирует удалённую операцию"},
                }
            ]
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "validation_failed")
        self.assertIn("serverId", result["error"]["fieldErrors"])
        self.assertFalse(Transaction.objects.filter(pk=deleted_id).exists())
        self.assertTrue(
            OfflineSyncTombstone.objects.filter(
                user=self.user,
                resource="transactions",
                object_id=deleted_id,
            ).exists()
        )

    def test_batch_continues_when_one_operation_conflicts(self):
        transaction = self.create_transaction(
            amount="100.00",
            description="Исходная операция batch",
        )
        base_version = transaction.updated_at
        server_version = base_version + timedelta(minutes=2)
        Transaction.objects.filter(pk=transaction.pk).update(
            description="Серверная версия batch",
            updated_at=server_version,
        )

        response = self._push(
            [
                {
                    "clientMutationId": "batch-conflict-operation",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": transaction.pk,
                    "baseVersion": base_version.isoformat(),
                    "payload": {"description": "Клиентская версия batch"},
                },
                {
                    "clientMutationId": "batch-applied-operation",
                    "resource": "transactions",
                    "action": "create",
                    "clientId": "local-batch-created-transaction",
                    "payload": {
                        "account": self.account.pk,
                        "category": self.expense_category.pk,
                        "type": "expense",
                        "amount": "15.00",
                        "operation_date": self.today.isoformat(),
                        "description": "Создано в том же batch",
                    },
                },
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "conflict")
        self.assertEqual(response.data["results"][1]["status"], "applied")
        self.assertTrue(Transaction.objects.filter(description="Создано в том же batch").exists())
        self.assertEqual(
            OfflineSyncOperation.objects.filter(
                client_mutation_id__in=["batch-conflict-operation", "batch-applied-operation"],
            ).count(),
            2,
        )

    def test_resolve_conflict_rejects_other_user_object(self):
        other_transaction = self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            amount="90.00",
            description="Чужая операция",
        )

        response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "transactions",
                "serverId": other_transaction.pk,
                "strategy": "client_wins",
                "payload": {"description": "Попытка изменить чужое"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("serverId", response.data["error"]["field_errors"])
        other_transaction.refresh_from_db()
        self.assertEqual(other_transaction.description, "Чужая операция")

    def test_server_wins_resolution_marks_logged_conflict_as_resolved(self):
        transaction = self.create_transaction(
            amount="100.00",
            description="Исходная версия для resolve",
        )
        base_version = transaction.updated_at
        server_version = base_version + timedelta(minutes=5)
        Transaction.objects.filter(pk=transaction.pk).update(
            description="Серверная версия для resolve",
            updated_at=server_version,
        )

        conflict_response = self._push(
            [
                {
                    "clientMutationId": "logged-conflict-to-resolve",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": transaction.pk,
                    "baseVersion": base_version.isoformat(),
                    "payload": {"description": "Клиентская версия для resolve"},
                }
            ]
        )
        self.assertEqual(conflict_response.status_code, 200)
        self.assertEqual(conflict_response.data["results"][0]["status"], "conflict")

        resolve_response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "transactions",
                "serverId": transaction.pk,
                "strategy": "server_wins",
            },
            format="json",
        )

        self.assertEqual(resolve_response.status_code, 200)
        self.assertEqual(resolve_response.data["status"], "resolved")
        operation = OfflineSyncOperation.objects.get(client_mutation_id="logged-conflict-to-resolve")
        self.assertEqual(operation.status, OfflineSyncOperationStatus.APPLIED)
        self.assertEqual(operation.error_data, {})
        self.assertEqual(operation.response_data["status"], "resolved")
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, "Серверная версия для resolve")

    def test_last_write_wins_without_client_timestamp_keeps_server_version(self):
        transaction = self.create_transaction(
            amount="100.00",
            description="Серверная версия без clientUpdatedAt",
        )
        base_version = transaction.updated_at
        server_version = base_version + timedelta(minutes=4)
        Transaction.objects.filter(pk=transaction.pk).update(
            description="Сервер изменил без clientUpdatedAt",
            updated_at=server_version,
        )

        response = self._push(
            [
                {
                    "clientMutationId": "lww-without-client-updated-at",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": transaction.pk,
                    "baseVersion": base_version.isoformat(),
                    "conflictStrategy": "last_write_wins",
                    "payload": {"description": "Клиент без clientUpdatedAt"},
                }
            ]
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["conflictResolution"]["finalStrategy"], "server_wins")
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, "Сервер изменил без clientUpdatedAt")
