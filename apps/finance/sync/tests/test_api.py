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
        self.assertEqual(response.data["maxBatchSize"], 100)

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
