from decimal import Decimal

from django.utils import timezone

from apps.finance.models import (
    Account,
    OfflineSyncOperation,
    OfflineSyncTombstone,
    Transaction,
)
from apps.finance.testing import FinanceAPITestCase


class OfflineSyncAPITests(FinanceAPITestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def test_meta_returns_supported_resources(self):
        response = self.client.get("/api/v1/finance/sync/meta/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schemaVersion"], 1)
        self.assertIn("accounts", response.data["supportedResources"])
        self.assertIn("transactions", response.data["supportedResources"])
        self.assertIn("dashboard", response.data["readOnlySnapshots"])
        self.assertIn("financialCalendar", response.data["readOnlySnapshots"])
        self.assertIn("accounts", response.data["writableResources"])
        self.assertIn("transactions", response.data["writableResources"])
        self.assertIn("receipts", response.data["readOnlyResources"])
        self.assertIn("goals", response.data["excludedResources"])
        self.assertIn("reports", response.data["excludedResources"])
        self.assertTrue(response.data["domainAreas"])
        self.assertEqual(response.data["maxBatchSize"], 100)

    def test_domains_endpoint_returns_offline_first_scope(self):
        response = self.client.get("/api/v1/finance/sync/domains/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["schemaVersion"], 1)
        self.assertIn("accounts", response.data["writableResources"])
        self.assertIn("categories", response.data["writableResources"])
        self.assertIn("transactions", response.data["writableResources"])
        self.assertIn("transactionTemplates", response.data["writableResources"])
        self.assertIn("plannedTransactions", response.data["writableResources"])
        self.assertIn("receipts", response.data["readOnlyResources"])
        self.assertIn("notifications", response.data["readOnlyResources"])
        self.assertIn("dashboard", response.data["readOnlySnapshots"])
        self.assertIn("financialCalendar", response.data["readOnlySnapshots"])
        self.assertIn("goals", response.data["excludedResources"])
        self.assertIn("reports", response.data["excludedResources"])

        domain_keys = [item["key"] for item in response.data["domainAreas"]]
        self.assertIn("core-finance", domain_keys)
        self.assertIn("planning", domain_keys)
        self.assertIn("analytics-snapshots", domain_keys)

    def test_domains_endpoint_marks_dashboard_and_calendar_as_read_only_snapshots(self):
        response = self.client.get("/api/v1/finance/sync/domains/")

        self.assertEqual(response.status_code, 200)
        analytics_area = next(
            item for item in response.data["domainAreas"]
            if item["key"] == "analytics-snapshots"
        )
        self.assertEqual(analytics_area["syncMode"], "read_only_snapshot")
        self.assertIn("dashboard", analytics_area["snapshots"])
        self.assertIn("financialCalendar", analytics_area["snapshots"])
        self.assertEqual(analytics_area["actions"], [])

    def test_bootstrap_returns_selected_resources_and_snapshots(self):
        self.create_transaction(amount="250.00")

        response = self.client.get(
            "/api/v1/finance/sync/bootstrap/",
            {
                "resources": "accounts,categories,transactions,dashboard,financialCalendar",
                "currency": "RUB",
                "period": "month",
                "calendarYear": self.today.year,
                "calendarMonth": self.today.month,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("syncToken", response.data)
        self.assertIn("accounts", response.data["resources"])
        self.assertIn("categories", response.data["resources"])
        self.assertIn("transactions", response.data["resources"])
        self.assertIn("dashboard", response.data["snapshots"])
        self.assertIn("financialCalendar", response.data["snapshots"])
        self.assertNotIn("goals", response.data["resources"])

    def test_pull_returns_upserted_and_deleted_since_token(self):
        sync_token = timezone.now()
        transaction = self.create_transaction(amount="100.00")
        Transaction.objects.filter(pk=transaction.pk).update(updated_at=timezone.now())
        OfflineSyncTombstone.objects.create(
            user=self.user,
            resource="accounts",
            object_id=999,
        )

        response = self.client.get(
            "/api/v1/finance/sync/pull/",
            {
                "since": sync_token.isoformat(),
                "resources": "transactions,accounts",
            },
        )

        self.assertEqual(response.status_code, 200)
        transaction_ids = [item["id"] for item in response.data["changes"]["transactions"]["upserted"]]
        self.assertIn(transaction.pk, transaction_ids)
        self.assertEqual(
            response.data["changes"]["accounts"]["deleted"][0]["id"],
            "999",
        )

    def test_push_create_transaction_is_idempotent(self):
        payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-1",
                    "resource": "transactions",
                    "action": "create",
                    "clientId": "local-tx-1",
                    "payload": {
                        "account": self.account.pk,
                        "category": self.expense_category.pk,
                        "type": "expense",
                        "amount": "110.00",
                        "operation_date": self.today.isoformat(),
                        "description": "Оффлайн операция",
                        "line_items": [
                            {
                                "name": "Товар",
                                "qty": 1,
                                "unit_price_rub": 110,
                                "sum_rub": 110,
                            }
                        ],
                    },
                }
            ],
        }

        first_response = self.client.post(
            "/api/v1/finance/sync/push/",
            payload,
            format="json",
        )
        second_response = self.client.post(
            "/api/v1/finance/sync/push/",
            payload,
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.data["results"][0]["status"], "applied")
        self.assertEqual(second_response.data["results"][0]["status"], "duplicate")
        self.assertEqual(Transaction.objects.filter(description="Оффлайн операция").count(), 1)
        transaction = Transaction.objects.get(description="Оффлайн операция")
        self.assertEqual(transaction.line_items.count(), 1)
        self.assertEqual(OfflineSyncOperation.objects.count(), 1)

    def test_push_update_conflict_returns_conflict_status(self):
        transaction = self.create_transaction(amount="100.00")
        base_version = transaction.updated_at
        Transaction.objects.filter(pk=transaction.pk).update(updated_at=timezone.now())

        payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-conflict",
                    "resource": "transactions",
                    "action": "update",
                    "serverId": transaction.pk,
                    "baseVersion": base_version.isoformat(),
                    "payload": {
                        "description": "Клиентское изменение",
                    },
                }
            ],
        }

        response = self.client.post(
            "/api/v1/finance/sync/push/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "conflict")
        self.assertEqual(response.data["results"][0]["error"]["code"], "sync_conflict")

    def test_push_delete_creates_tombstone(self):
        account = Account.objects.create(
            user=self.user,
            name="Счёт для удаления",
            initial_balance=Decimal("0.00"),
            balance=Decimal("0.00"),
            currency="RUB",
        )
        payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-delete-account",
                    "resource": "accounts",
                    "action": "delete",
                    "serverId": account.pk,
                    "baseVersion": account.updated_at.isoformat(),
                    "payload": {},
                }
            ],
        }

        response = self.client.post(
            "/api/v1/finance/sync/push/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "applied")
        self.assertFalse(Account.objects.filter(pk=account.pk).exists())
        self.assertTrue(
            OfflineSyncTombstone.objects.filter(
                user=self.user,
                resource="accounts",
                object_id=account.pk,
            ).exists()
        )

    def test_push_rejects_empty_operations_batch(self):
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("operations", response.data["error"]["field_errors"])

    def test_push_rejects_duplicate_mutation_ids_inside_batch(self):
        operation = {
            "clientMutationId": "same-mutation",
            "resource": "transactions",
            "action": "create",
            "clientId": "local-tx-1",
            "payload": {
                "account": self.account.pk,
                "category": self.expense_category.pk,
                "type": "expense",
                "amount": "10.00",
                "operation_date": self.today.isoformat(),
            },
        }
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [operation, {**operation}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("operations", response.data["error"]["field_errors"])

    def test_push_duplicate_mutation_with_changed_payload_returns_failed(self):
        payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-reuse",
                    "resource": "transactions",
                    "action": "create",
                    "clientId": "local-tx-reuse",
                    "payload": {
                        "account": self.account.pk,
                        "category": self.expense_category.pk,
                        "type": "expense",
                        "amount": "10.00",
                        "operation_date": self.today.isoformat(),
                    },
                }
            ],
        }
        first_response = self.client.post("/api/v1/finance/sync/push/", payload, format="json")
        payload["operations"][0]["payload"]["amount"] = "20.00"
        second_response = self.client.post("/api/v1/finance/sync/push/", payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        result = second_response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "duplicate_mutation_payload_mismatch")
        self.assertEqual(Transaction.objects.filter(amount=Decimal("10.00")).count(), 1)
        self.assertFalse(Transaction.objects.filter(amount=Decimal("20.00")).exists())

    def test_push_create_requires_local_client_id(self):
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [
                    {
                        "clientMutationId": "mutation-without-client-id",
                        "resource": "transactions",
                        "action": "create",
                        "payload": {
                            "account": self.account.pk,
                            "category": self.expense_category.pk,
                            "type": "expense",
                            "amount": "10.00",
                            "operation_date": self.today.isoformat(),
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "client_id_required")
        self.assertFalse(Transaction.objects.filter(amount=Decimal("10.00")).exists())

    def test_push_create_with_same_client_id_is_treated_as_duplicate(self):
        first_payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-local-1",
                    "resource": "transactions",
                    "action": "create",
                    "clientId": "local-transaction-duplicate",
                    "payload": {
                        "account": self.account.pk,
                        "category": self.expense_category.pk,
                        "type": "expense",
                        "amount": "10.00",
                        "operation_date": self.today.isoformat(),
                        "description": "Локальная операция",
                    },
                }
            ],
        }
        second_payload = {
            "clientId": "web-pwa",
            "deviceId": "browser-1",
            "operations": [
                {
                    "clientMutationId": "mutation-local-2",
                    "resource": "transactions",
                    "action": "create",
                    "clientId": "local-transaction-duplicate",
                    "payload": {
                        "account": self.account.pk,
                        "category": self.expense_category.pk,
                        "type": "expense",
                        "amount": "10.00",
                        "operation_date": self.today.isoformat(),
                        "description": "Локальная операция",
                    },
                }
            ],
        }

        first_response = self.client.post("/api/v1/finance/sync/push/", first_payload, format="json")
        second_response = self.client.post("/api/v1/finance/sync/push/", second_payload, format="json")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.data["results"][0]["status"], "applied")
        self.assertEqual(second_response.data["results"][0]["status"], "duplicate")
        self.assertEqual(Transaction.objects.filter(description="Локальная операция").count(), 1)

    def test_push_update_payload_id_mismatch_returns_failed(self):
        transaction = self.create_transaction(amount="100.00")
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [
                    {
                        "clientMutationId": "mutation-id-mismatch",
                        "resource": "transactions",
                        "action": "update",
                        "serverId": transaction.pk,
                        "baseVersion": transaction.updated_at.isoformat(),
                        "payload": {
                            "id": transaction.pk + 1,
                            "description": "Некорректное изменение",
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "server_id_payload_mismatch")

    def test_push_rejects_other_user_server_id_without_500(self):
        other_transaction = self.create_transaction(
            user=self.other_user,
            account=self.other_account,
            category=self.other_category,
            amount="100.00",
        )
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [
                    {
                        "clientMutationId": "mutation-other-user",
                        "resource": "transactions",
                        "action": "update",
                        "serverId": other_transaction.pk,
                        "payload": {"description": "Попытка изменить чужую операцию"},
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "validation_failed")

    def test_push_read_only_snapshot_returns_failed_result(self):
        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [
                    {
                        "clientMutationId": "mutation-dashboard",
                        "resource": "dashboard",
                        "action": "update",
                        "serverId": 1,
                        "payload": {"id": 1},
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "read_only_snapshot_resource")

    def test_push_conflict_response_contains_manual_resolution_data(self):
        transaction = self.create_transaction(amount="100.00", description="Серверная версия")
        base_version = transaction.updated_at
        Transaction.objects.filter(pk=transaction.pk).update(
            description="Изменено на сервере",
            updated_at=timezone.now(),
        )

        response = self.client.post(
            "/api/v1/finance/sync/push/",
            {
                "clientId": "web-pwa",
                "deviceId": "browser-1",
                "operations": [
                    {
                        "clientMutationId": "mutation-rich-conflict",
                        "resource": "transactions",
                        "action": "update",
                        "serverId": transaction.pk,
                        "baseVersion": base_version.isoformat(),
                        "payload": {
                            "description": "Клиентская версия",
                        },
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["error"]["code"], "sync_conflict")
        self.assertIn("clientData", result["data"])
        self.assertIn("serverData", result["data"])
        self.assertIn("conflictFields", result["data"])
        self.assertIn("server_wins", result["data"]["availableStrategies"])
        self.assertIn("client_wins", result["data"]["availableStrategies"])
        self.assertIn("merge", result["data"]["availableStrategies"])
        self.assertEqual(result["data"]["clientData"]["description"], "Клиентская версия")
        self.assertEqual(result["data"]["serverData"]["description"], "Изменено на сервере")
        self.assertEqual(result["data"]["conflictFields"][0]["field"], "description")

    def test_resolve_conflict_server_wins_keeps_server_version(self):
        transaction = self.create_transaction(amount="100.00", description="Серверная версия")

        response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "transactions",
                "serverId": transaction.pk,
                "strategy": "server_wins",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "resolved")
        self.assertEqual(response.data["strategy"], "server_wins")
        self.assertEqual(response.data["data"]["description"], "Серверная версия")
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, "Серверная версия")

    def test_resolve_conflict_client_wins_applies_client_payload(self):
        transaction = self.create_transaction(amount="100.00", description="Серверная версия")

        response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "transactions",
                "serverId": transaction.pk,
                "strategy": "client_wins",
                "payload": {
                    "description": "Клиентская версия",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "resolved")
        self.assertEqual(response.data["strategy"], "client_wins")
        self.assertEqual(response.data["data"]["description"], "Клиентская версия")
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, "Клиентская версия")

    def test_resolve_conflict_merge_applies_manual_payload(self):
        transaction = self.create_transaction(amount="100.00", description="Серверная версия")

        response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "transactions",
                "serverId": transaction.pk,
                "strategy": "merge",
                "payload": {
                    "description": "Ручной merge",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "resolved")
        self.assertEqual(response.data["strategy"], "merge")
        self.assertEqual(response.data["data"]["description"], "Ручной merge")
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, "Ручной merge")

    def test_resolve_conflict_rejects_read_only_snapshot(self):
        response = self.client.post(
            "/api/v1/finance/sync/conflicts/resolve/",
            {
                "resource": "dashboard",
                "serverId": 1,
                "strategy": "server_wins",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("resource", response.data["error"]["field_errors"])
