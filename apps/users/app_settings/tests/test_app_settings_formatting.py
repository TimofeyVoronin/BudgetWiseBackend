from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.currencies.services import ensure_user_currencies
from apps.users.app_settings.formatting import (
    build_app_formatting_context,
    format_app_date,
    format_app_money,
    format_app_number,
    get_user_app_today,
)
from apps.users.models import AppDateFormat, AppNumberFormat, UserAppSettings


User = get_user_model()


class AppSettingsFormattingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="formatting-user",
            email="formatting-user@example.com",
            password="StrongPass123!",
        )
        ensure_user_currencies(self.user)

    def test_ru_formatting_uses_saved_date_number_and_currency_symbol(self):
        UserAppSettings.objects.create(
            user=self.user,
            timezone="Asia/Krasnoyarsk",
            date_format=AppDateFormat.DD_MM_YYYY,
            number_format=AppNumberFormat.RU_RU,
            default_currency="RUB",
        )

        context = build_app_formatting_context(self.user)

        self.assertEqual(format_app_date(date(2026, 5, 24), context), "24.05.2026")
        self.assertEqual(format_app_number(Decimal("1234567.895"), context), "1 234 567,90")
        self.assertEqual(format_app_money(Decimal("1234.5"), context, user=self.user), "1 234,50 ₽")

    def test_en_formatting_uses_saved_date_number_and_default_currency(self):
        UserAppSettings.objects.create(
            user=self.user,
            timezone="UTC",
            date_format=AppDateFormat.YYYY_MM_DD,
            number_format=AppNumberFormat.EN_US,
            default_currency="USD",
        )

        context = build_app_formatting_context(self.user)

        self.assertEqual(format_app_date(date(2026, 5, 24), context), "2026-05-24")
        self.assertEqual(format_app_number(Decimal("-1234567.895"), context), "-1,234,567.90")
        self.assertEqual(format_app_money(Decimal("-1234.5"), context, user=self.user), "-1,234.50 $")

    def test_datetime_date_label_is_converted_to_user_timezone(self):
        UserAppSettings.objects.create(
            user=self.user,
            timezone="Asia/Krasnoyarsk",
            date_format=AppDateFormat.DD_MM_YYYY,
            number_format=AppNumberFormat.RU_RU,
            default_currency="RUB",
        )
        utc_datetime = datetime(2026, 5, 23, 20, 30, tzinfo=datetime_timezone.utc)

        context = build_app_formatting_context(self.user)

        self.assertEqual(format_app_date(utc_datetime, context), "24.05.2026")

    @patch("apps.users.app_settings.formatting.django_timezone.now")
    def test_get_user_app_today_uses_saved_timezone(self, mocked_now):
        mocked_now.return_value = datetime(2026, 5, 23, 20, 30, tzinfo=datetime_timezone.utc)
        UserAppSettings.objects.create(
            user=self.user,
            timezone="UTC",
            date_format=AppDateFormat.DD_MM_YYYY,
            number_format=AppNumberFormat.RU_RU,
            default_currency="RUB",
        )

        self.assertEqual(get_user_app_today(self.user), date(2026, 5, 23))

        settings = UserAppSettings.objects.get(user=self.user)
        settings.timezone = "Asia/Krasnoyarsk"
        settings.save(update_fields=["timezone", "updated_at"])

        self.assertEqual(get_user_app_today(self.user), date(2026, 5, 24))

    def test_invalid_timezone_override_falls_back_to_default_timezone(self):
        UserAppSettings.objects.create(
            user=self.user,
            timezone="UTC",
            date_format=AppDateFormat.DD_MM_YYYY,
            number_format=AppNumberFormat.RU_RU,
            default_currency="RUB",
        )
        utc_datetime = datetime(2026, 5, 23, 20, 30, tzinfo=datetime_timezone.utc)

        context = build_app_formatting_context(self.user, timezone_value="Wrong/Timezone")

        self.assertEqual(context.timezone_name, "Wrong/Timezone")
        self.assertEqual(format_app_date(utc_datetime, context), "24.05.2026")
