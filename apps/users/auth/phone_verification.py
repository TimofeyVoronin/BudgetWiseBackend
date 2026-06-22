from __future__ import annotations

import base64
import json
import logging
import random
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import phonenumbers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.crypto import constant_time_compare, salted_hmac
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.users.auth.verification import ensure_verified_contact
from apps.users.models import PhoneVerificationCode


logger = logging.getLogger("apps")

PHONE_VERIFICATION_ACCEPTED_MESSAGE = "Код подтверждения телефона отправлен."
PHONE_ALREADY_CONFIRMED_MESSAGE = "Телефон уже подтверждён."
PHONE_VERIFICATION_SUCCESS_MESSAGE = "Телефон подтверждён."
PHONE_VERIFICATION_PURPOSE = "phone_verification"

PHONE_VERIFICATION_DISABLED_CODE = "phone_verification_disabled"
PHONE_VERIFICATION_RECENTLY_SENT_CODE = "phone_verification_recently_sent"
PHONE_VERIFICATION_INVALID_CODE = "phone_verification_invalid_code"
PHONE_VERIFICATION_EXPIRED_CODE = "phone_verification_expired"
PHONE_VERIFICATION_TOO_MANY_ATTEMPTS_CODE = "phone_verification_too_many_attempts"
PHONE_VERIFICATION_INVALID_PHONE_CODE = "invalid_phone"
PHONE_VERIFICATION_PHONE_UNIQUE_CODE = "unique"


class PhoneVerificationProviderError(Exception):
    """Raised when a phone verification provider cannot send a message."""


def phone_verification_enabled() -> bool:
    return bool(getattr(settings, "PHONE_VERIFICATION_ENABLED", False))


def normalize_phone_number(raw_phone: str, *, default_region: str | None = None) -> str:
    phone = str(raw_phone or "").strip()
    if not phone:
        return ""

    region = default_region or getattr(settings, "PHONE_DEFAULT_REGION", "RU")

    try:
        parsed_phone = phonenumbers.parse(phone, None if phone.startswith("+") else region)
    except phonenumbers.NumberParseException:
        raise serializers.ValidationError(
            "Некорректный номер телефона.",
            code=PHONE_VERIFICATION_INVALID_PHONE_CODE,
        )

    if not phonenumbers.is_possible_number(parsed_phone) or not phonenumbers.is_valid_number(parsed_phone):
        raise serializers.ValidationError(
            "Некорректный номер телефона.",
            code=PHONE_VERIFICATION_INVALID_PHONE_CODE,
        )

    return phonenumbers.format_number(parsed_phone, phonenumbers.PhoneNumberFormat.E164)




def normalize_stored_phone_number(raw_phone: str) -> str:
    phone = str(raw_phone or "").strip()
    if not phone:
        return ""

    try:
        return normalize_phone_number(phone)
    except serializers.ValidationError:
        return phone


def ensure_phone_is_available(phone: str, *, user) -> None:
    User = get_user_model()
    if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
        raise serializers.ValidationError(
            "Этот телефон уже используется другим пользователем.",
            code=PHONE_VERIFICATION_PHONE_UNIQUE_CODE,
        )


def generate_phone_verification_code() -> str:
    return f"{random.SystemRandom().randint(0, 999999):06d}"


def build_phone_verification_code_hash(*, phone: str, code: str) -> str:
    value = f"{phone}:{code}"
    return salted_hmac(
        getattr(settings, "PHONE_VERIFICATION_CODE_SALT", "budgetwise.phone-verification"),
        value,
    ).hexdigest()


def check_phone_verification_code(*, phone: str, code: str, expected_hash: str) -> bool:
    actual_hash = build_phone_verification_code_hash(phone=phone, code=code)
    return constant_time_compare(actual_hash, expected_hash)


def request_phone_verification(user, *, phone: str | None = None, force: bool = False) -> dict[str, Any]:
    if not phone_verification_enabled():
        raise ValidationError(
            {
                "detail": [
                    serializers.ErrorDetail(
                        "Подтверждение телефона выключено.",
                        code=PHONE_VERIFICATION_DISABLED_CODE,
                    )
                ]
            }
        )

    normalized_phone = normalize_phone_number(phone or user.phone)
    if not normalized_phone:
        raise ValidationError(
            {
                "phone": [
                    serializers.ErrorDetail(
                        "Укажите номер телефона.",
                        code="required",
                    )
                ]
            }
        )

    ensure_phone_is_available(normalized_phone, user=user)

    now = timezone.now()
    cooldown_seconds = int(getattr(settings, "PHONE_VERIFICATION_RESEND_COOLDOWN_SECONDS", 60))
    lifetime_seconds = int(getattr(settings, "PHONE_VERIFICATION_CODE_TTL_SECONDS", 15 * 60))
    code = generate_phone_verification_code()
    code_hash = build_phone_verification_code_hash(phone=normalized_phone, code=code)

    with transaction.atomic():
        User = get_user_model()
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        old_phone = (locked_user.phone or "").strip()
        comparable_old_phone = normalize_stored_phone_number(old_phone)
        phone_changed = comparable_old_phone != normalized_phone

        if phone_changed and old_phone:
            ensure_verified_contact(locked_user)

        last_code = (
            PhoneVerificationCode.objects
            .filter(
                user=locked_user,
                phone=normalized_phone,
                confirmed_at__isnull=True,
            )
            .order_by("-sent_at", "-id")
            .first()
        )

        if not force and last_code is not None:
            next_allowed_at = last_code.sent_at + timedelta(seconds=cooldown_seconds)
            if now < next_allowed_at:
                retry_after_seconds = max(1, int((next_allowed_at - now).total_seconds()))
                raise serializers.ValidationError(
                    {
                        "detail": [
                            serializers.ErrorDetail(
                                f"Повторно отправить код можно через {retry_after_seconds} сек.",
                                code=PHONE_VERIFICATION_RECENTLY_SENT_CODE,
                            )
                        ]
                    }
                )

        if phone_changed:
            locked_user.phone = normalized_phone
            locked_user.phone_verified = False
            locked_user.phone_verified_at = None
            locked_user.save(update_fields=["phone", "phone_verified", "phone_verified_at"])

        verification_code = PhoneVerificationCode.objects.create(
            user=locked_user,
            phone=normalized_phone,
            code_hash=code_hash,
            expires_at=now + timedelta(seconds=lifetime_seconds),
            sent_at=now,
        )

    if getattr(settings, "PHONE_VERIFICATION_SEND_ASYNC", True):
        from apps.users.tasks import send_phone_verification_code_task

        task_result = send_phone_verification_code_task.delay(verification_code.id, code)
        return {
            "sent": False,
            "queued": True,
            "task_id": str(task_result.id),
            "phone": normalized_phone,
            "phone_changed": phone_changed,
            "old_phone": old_phone,
            "detail": PHONE_VERIFICATION_ACCEPTED_MESSAGE,
        }

    send_phone_verification_code(verification_code=verification_code, code=code)
    return {
        "sent": True,
        "queued": False,
        "phone": normalized_phone,
        "phone_changed": phone_changed,
        "old_phone": old_phone,
        "detail": PHONE_VERIFICATION_ACCEPTED_MESSAGE,
    }


def confirm_phone_verification(user, *, phone: str, code: str) -> dict[str, Any]:
    if not phone_verification_enabled():
        raise ValidationError(
            {
                "detail": [
                    serializers.ErrorDetail(
                        "Подтверждение телефона выключено.",
                        code=PHONE_VERIFICATION_DISABLED_CODE,
                    )
                ]
            }
        )

    normalized_phone = normalize_phone_number(phone)
    code = str(code or "").strip()
    max_attempts = int(getattr(settings, "PHONE_VERIFICATION_MAX_ATTEMPTS", 5))

    if not code:
        raise ValidationError(
            {
                "code": [
                    serializers.ErrorDetail(
                        "Укажите код подтверждения.",
                        code="required",
                    )
                ]
            }
        )

    with transaction.atomic():
        verification_code = (
            PhoneVerificationCode.objects
            .select_for_update()
            .filter(
                user=user,
                phone=normalized_phone,
                confirmed_at__isnull=True,
            )
            .order_by("-sent_at", "-id")
            .first()
        )

        if verification_code is None:
            raise ValidationError(
                {
                    "code": [
                        serializers.ErrorDetail(
                            "Неверный код подтверждения телефона.",
                            code=PHONE_VERIFICATION_INVALID_CODE,
                        )
                    ]
                }
            )

        if verification_code.is_expired:
            raise ValidationError(
                {
                    "code": [
                        serializers.ErrorDetail(
                            "Срок действия кода подтверждения истёк.",
                            code=PHONE_VERIFICATION_EXPIRED_CODE,
                        )
                    ]
                }
            )

        if verification_code.attempts_count >= max_attempts:
            raise ValidationError(
                {
                    "code": [
                        serializers.ErrorDetail(
                            "Превышено количество попыток ввода кода.",
                            code=PHONE_VERIFICATION_TOO_MANY_ATTEMPTS_CODE,
                        )
                    ]
                }
            )

        invalid_code_error = None

        if not check_phone_verification_code(
            phone=normalized_phone,
            code=code,
            expected_hash=verification_code.code_hash,
        ):
            verification_code.attempts_count += 1
            verification_code.save(update_fields=["attempts_count"])
            invalid_code_error = ValidationError(
                {
                    "code": [
                        serializers.ErrorDetail(
                            "Неверный код подтверждения телефона.",
                            code=PHONE_VERIFICATION_INVALID_CODE,
                        )
                    ]
                }
            )
        else:
            now = timezone.now()
            verification_code.confirmed_at = now
            verification_code.save(update_fields=["confirmed_at"])

            User = get_user_model()
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            ensure_phone_is_available(normalized_phone, user=locked_user)
            locked_user.phone = normalized_phone
            locked_user.phone_verified = True
            locked_user.phone_verified_at = now
            locked_user.save(update_fields=["phone", "phone_verified", "phone_verified_at"])

    if invalid_code_error is not None:
        raise invalid_code_error

    return {
        "phone": normalized_phone,
        "isPhoneVerified": True,
        "phoneVerificationRequired": False,
        "detail": PHONE_VERIFICATION_SUCCESS_MESSAGE,
    }


def send_phone_verification_code(*, verification_code: PhoneVerificationCode, code: str) -> dict[str, Any]:
    provider = str(getattr(settings, "PHONE_VERIFICATION_PROVIDER", "console") or "console").strip().lower()

    if provider == "console":
        return send_phone_verification_code_console(
            verification_code=verification_code,
            code=code,
        )

    if provider == "smsaero":
        return send_phone_verification_code_smsaero(
            verification_code=verification_code,
            code=code,
        )

    raise PhoneVerificationProviderError(
        f"Unsupported phone verification provider: {provider}"
    )


def send_phone_verification_code_console(*, verification_code: PhoneVerificationCode, code: str) -> dict[str, Any]:
    logger.info(
        (
            "Phone verification code generated. "
            "provider=console user_id=%s phone=%s code=%s expires_at=%s"
        ),
        verification_code.user_id,
        verification_code.phone,
        code,
        verification_code.expires_at.isoformat(),
    )
    return {
        "sent": True,
        "provider": "console",
        "phone": verification_code.phone,
        "verification_code_id": verification_code.id,
    }


def build_phone_verification_sms_text(*, code: str) -> str:
    template = getattr(
        settings,
        "PHONE_VERIFICATION_SMS_TEXT_TEMPLATE",
        "Код подтверждения BudgetWise: {code}. Никому не сообщайте этот код.",
    )
    return str(template).format(code=code)


def format_phone_for_smsaero(phone: str) -> int:
    normalized_phone = normalize_phone_number(phone)
    return int(normalized_phone.lstrip("+"))


def send_phone_verification_code_smsaero(*, verification_code: PhoneVerificationCode, code: str) -> dict[str, Any]:
    email = str(getattr(settings, "SMSAERO_EMAIL", "") or "").strip()
    api_key = str(getattr(settings, "SMSAERO_API_KEY", "") or "").strip()
    sign = str(getattr(settings, "SMSAERO_SIGN", "SMS Aero") or "SMS Aero").strip()

    if not email or not api_key:
        raise PhoneVerificationProviderError(
            "SMS Aero provider is not configured. Set SMSAERO_EMAIL and SMSAERO_API_KEY."
        )

    phone_number = format_phone_for_smsaero(verification_code.phone)
    message_text = build_phone_verification_sms_text(code=code)
    payload = {
        "number": phone_number,
        "text": message_text,
        "sign": sign,
    }

    response_data = send_smsaero_request(
        selector="sms/testsend" if getattr(settings, "SMSAERO_TEST_MODE", False) else "sms/send",
        payload=payload,
        email=email,
        api_key=api_key,
    )

    sms_id = response_data.get("id") if isinstance(response_data, dict) else None
    logger.info(
        "Phone verification SMS sent. provider=smsaero user_id=%s phone=%s sms_id=%s test_mode=%s",
        verification_code.user_id,
        verification_code.phone,
        sms_id,
        bool(getattr(settings, "SMSAERO_TEST_MODE", False)),
    )
    return {
        "sent": True,
        "provider": "smsaero",
        "phone": verification_code.phone,
        "verification_code_id": verification_code.id,
        "sms_id": sms_id,
        "response": response_data,
    }


def build_smsaero_url(selector: str) -> str:
    base_url = str(getattr(settings, "SMSAERO_BASE_URL", "https://gate.smsaero.ru/v2") or "").strip()
    if not base_url:
        base_url = "https://gate.smsaero.ru/v2"
    return f"{base_url.rstrip('/')}/{selector.lstrip('/')}"


def build_smsaero_auth_header(*, email: str, api_key: str) -> str:
    credentials = f"{email}:{api_key}".encode("utf-8")
    return "Basic " + base64.b64encode(credentials).decode("ascii")


def send_smsaero_request(*, selector: str, payload: dict[str, Any], email: str, api_key: str) -> dict[str, Any]:
    url = build_smsaero_url(selector)
    timeout = int(getattr(settings, "SMSAERO_TIMEOUT_SECONDS", 10))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": build_smsaero_auth_header(email=email, api_key=api_key),
            "User-Agent": "BudgetWiseBackend/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        raise PhoneVerificationProviderError(
            f"SMS Aero request failed with HTTP {exc.code}: {extract_smsaero_error_message(raw_body)}"
        ) from exc
    except URLError as exc:
        raise PhoneVerificationProviderError(f"SMS Aero connection error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PhoneVerificationProviderError("SMS Aero request timed out.") from exc

    try:
        content = json.loads(raw_body or "{}")
    except ValueError as exc:
        raise PhoneVerificationProviderError("SMS Aero returned an invalid JSON response.") from exc

    return parse_smsaero_response(content)


def extract_smsaero_error_message(raw_body: str) -> str:
    try:
        content = json.loads(raw_body or "{}")
    except ValueError:
        return raw_body[:300] or "empty response"

    return (
        content.get("message")
        or content.get("reason")
        or content.get("result")
        or str(content)
    )


def parse_smsaero_response(content: dict[str, Any]) -> dict[str, Any]:
    result = content.get("result")
    if result == "no credits":
        raise PhoneVerificationProviderError("SMS Aero balance is too low to send SMS.")
    if result == "reject":
        raise PhoneVerificationProviderError(content.get("reason") or "SMS Aero rejected the request.")
    if not content.get("success"):
        raise PhoneVerificationProviderError(
            content.get("message")
            or content.get("reason")
            or content.get("result")
            or "SMS Aero returned an unsuccessful response."
        )

    data = content.get("data")
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return {"data": data}
