from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


User = get_user_model()


class UserProfileMeAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("profile-me")
        self.user = User.objects.create_user(
            username="profile_user",
            email="profile-user@example.com",
            password="profile-password-123",
            first_name="Иван",
            last_name="Иванов",
            middle_name="Иванович",
            phone="+79990000000",
            city="Красноярск",
            bio="Backend developer",
        )

    def test_profile_me_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["status_code"], 401)

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_get_profile_me_returns_profile_data(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["username"], "profile_user")
        self.assertEqual(response.data["email"], "profile-user@example.com")
        self.assertEqual(response.data["firstName"], "Иван")
        self.assertEqual(response.data["lastName"], "Иванов")
        self.assertEqual(response.data["middleName"], "Иванович")
        self.assertEqual(response.data["fullName"], "Иванов Иван Иванович")
        self.assertEqual(response.data["phone"], "+79990000000")
        self.assertEqual(response.data["city"], "Красноярск")
        self.assertEqual(response.data["bio"], "Backend developer")
        self.assertIsNone(response.data["avatarUrl"])
        self.assertFalse(response.data["isEmailVerified"])
        self.assertFalse(response.data["emailVerificationEnabled"])
        self.assertFalse(response.data["isPhoneVerified"])
        self.assertFalse(response.data["phoneVerificationEnabled"])
        self.assertIn("createdAt", response.data)
        self.assertIn("updatedAt", response.data)

    def test_put_profile_me_updates_optional_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            self.url,
            {
                "firstName": "Тимофей",
                "lastName": "Воронин",
                "middleName": "Викторович",
                "phone": "+7 (999) 111-22-33",
                "city": "Красноярск",
                "bio": "Backend Python Developer",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["firstName"], "Тимофей")
        self.assertEqual(response.data["lastName"], "Воронин")
        self.assertEqual(response.data["middleName"], "Викторович")
        self.assertEqual(response.data["fullName"], "Воронин Тимофей Викторович")
        self.assertEqual(response.data["phone"], "+7 (999) 111-22-33")
        self.assertEqual(response.data["city"], "Красноярск")
        self.assertEqual(response.data["bio"], "Backend Python Developer")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Тимофей")
        self.assertEqual(self.user.last_name, "Воронин")
        self.assertEqual(self.user.middle_name, "Викторович")
        self.assertEqual(self.user.phone, "+7 (999) 111-22-33")
        self.assertEqual(self.user.city, "Красноярск")
        self.assertEqual(self.user.bio, "Backend Python Developer")

    def test_patch_profile_me_updates_partially_and_does_not_change_email(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            self.url,
            {
                "city": "Москва",
                "email": "hacker@example.com",
                "username": "hacker",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["city"], "Москва")
        self.assertEqual(response.data["email"], "profile-user@example.com")
        self.assertEqual(response.data["username"], "profile_user")

        self.user.refresh_from_db()
        self.assertEqual(self.user.city, "Москва")
        self.assertEqual(self.user.email, "profile-user@example.com")
        self.assertEqual(self.user.username, "profile_user")

    def test_profile_me_validates_phone_name_city_and_bio(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            self.url,
            {
                "firstName": "Тимофей123",
                "phone": "phone",
                "city": "Красноярск<script>",
                "bio": "x" * 501,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        field_errors = response.data["error"]["field_errors"]
        self.assertIn("firstName", field_errors)
        self.assertIn("phone", field_errors)
        self.assertIn("city", field_errors)
        self.assertIn("bio", field_errors)

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_profile_me_returns_email_verification_enabled(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["emailVerificationEnabled"])
        self.assertTrue(response.data["isEmailVerified"])

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_patch_profile_allows_first_phone_add_without_verified_contact(self):
        self.user.phone = ""
        self.user.email_verified = False
        self.user.phone_verified = False
        self.user.save(update_fields=["phone", "email_verified", "phone_verified"])
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            self.url,
            {"phone": "+79990000000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+79990000000")

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_patch_profile_rejects_existing_phone_change_without_verified_contact(self):
        self.user.email_verified = False
        self.user.phone_verified = False
        self.user.save(update_fields=["email_verified", "phone_verified"])
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            self.url,
            {"phone": "+79991112233"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "email_not_verified")

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_patch_profile_allows_existing_phone_change_with_verified_email(self):
        self.user.email_verified = True
        self.user.phone_verified = False
        self.user.save(update_fields=["email_verified", "phone_verified"])
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            self.url,
            {"phone": "+79991112233"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+79991112233")

