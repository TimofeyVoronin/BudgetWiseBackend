from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


User = get_user_model()


class UsersAdminAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="demo",
            email="demo@example.com",
            password="demo-password-123",
        )
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="other-password-123",
        )

    def test_regular_user_cannot_access_users_list(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("users:user-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 403)

    def test_admin_can_crud_users(self):
        self.client.force_authenticate(user=self.admin)

        list_response = self.client.get(reverse("users:user-list"))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_response.data["count"], 3)

        create_response = self.client.post(
            reverse("users:user-list"),
            data={
                "username": "created_user",
                "email": "created_user@example.com",
                "password": "created-password-123",
                "first_name": "Created",
                "last_name": "User",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        created_user_id = create_response.data["id"]
        created_user = User.objects.get(pk=created_user_id)
        self.assertTrue(created_user.check_password("created-password-123"))

        detail_response = self.client.get(
            reverse("users:user-detail", kwargs={"pk": created_user_id})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["username"], "created_user")

        update_response = self.client.patch(
            reverse("users:user-detail", kwargs={"pk": created_user_id}),
            data={
                "first_name": "Updated",
                "is_staff": True,
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["first_name"], "Updated")
        self.assertTrue(update_response.data["is_staff"])

        delete_response = self.client.delete(
            reverse("users:user-detail", kwargs={"pk": created_user_id})
        )

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

        created_user.refresh_from_db()
        self.assertFalse(created_user.is_active)

    def test_admin_cannot_deactivate_self(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            reverse("users:user-detail", kwargs={"pk": self.admin.id})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 400)

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_invalid_filters_return_bad_request(self):
        self.client.force_authenticate(user=self.admin)

        invalid_bool_response = self.client.get(
            reverse("users:user-list"),
            data={
                "is_staff": "wrong",
            },
        )

        self.assertEqual(
            invalid_bool_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(invalid_bool_response.data["success"])

        invalid_ordering_response = self.client.get(
            reverse("users:user-list"),
            data={
                "ordering": "wrong",
            },
        )

        self.assertEqual(
            invalid_ordering_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(invalid_ordering_response.data["success"])

    def test_admin_cannot_create_user_with_duplicate_email(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            reverse("users:user-list"),
            data={
                "username": "new_user",
                "email": self.user.email,
                "password": "new-password-123",
                "first_name": "New",
                "last_name": "User",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("email", response.data["error"]["field_errors"])
