from __future__ import annotations

from django.conf import settings
from rest_framework.exceptions import ErrorDetail, PermissionDenied


EMAIL_NOT_VERIFIED_CODE = "email_not_verified"
EMAIL_NOT_VERIFIED_MESSAGE = "Для выполнения действия подтвердите email или телефон."


def email_verification_enabled() -> bool:
    return bool(getattr(settings, "EMAIL_VERIFICATION_ENABLED", False))


def is_email_verified(user) -> bool:
    if not email_verification_enabled():
        return False
    return bool(getattr(user, "email_verified", False))


def is_phone_verified(user) -> bool:
    return bool(getattr(user, "phone_verified", False))


def has_verified_contact(user) -> bool:
    if not email_verification_enabled():
        return True
    return bool(is_email_verified(user) or is_phone_verified(user))


def email_verification_required(user) -> bool:
    return bool(email_verification_enabled() and not is_email_verified(user))


def ensure_verified_contact(user) -> None:
    if has_verified_contact(user):
        return

    raise PermissionDenied(
        ErrorDetail(EMAIL_NOT_VERIFIED_MESSAGE, code=EMAIL_NOT_VERIFIED_CODE),
    )
