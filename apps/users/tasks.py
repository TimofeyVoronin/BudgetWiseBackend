from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.contrib.auth import get_user_model

from apps.users.auth.email_confirmation import send_email_confirmation
from apps.users.auth.phone_verification import send_phone_verification_code
from apps.users.models import PhoneVerificationCode


logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.users.send_email_confirmation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_email_confirmation_task(self, user_id: int) -> dict[str, Any]:
    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()

    if user is None:
        logger.warning(
            "Email confirmation task skipped because user does not exist. task_id=%s user_id=%s",
            self.request.id,
            user_id,
        )
        return {
            "sent": False,
            "user_id": user_id,
            "reason": "user_not_found",
        }

    sent_count = send_email_confirmation(user)
    logger.info(
        "Email confirmation task finished. task_id=%s user_id=%s sent_count=%s",
        self.request.id,
        user.id,
        sent_count,
    )
    return {
        "sent": bool(sent_count),
        "sent_count": sent_count,
        "user_id": user.id,
        "email": user.email,
    }

@shared_task(
    bind=True,
    name="apps.users.send_phone_verification_code",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_phone_verification_code_task(self, verification_code_id: int, code: str) -> dict[str, Any]:
    verification_code = (
        PhoneVerificationCode.objects
        .select_related("user")
        .filter(pk=verification_code_id)
        .first()
    )

    if verification_code is None:
        logger.warning(
            "Phone verification task skipped because code does not exist. task_id=%s verification_code_id=%s",
            self.request.id,
            verification_code_id,
        )
        return {
            "sent": False,
            "verification_code_id": verification_code_id,
            "reason": "verification_code_not_found",
        }

    result = send_phone_verification_code(
        verification_code=verification_code,
        code=code,
    )
    logger.info(
        "Phone verification task finished. task_id=%s user_id=%s phone=%s provider=%s sent=%s",
        self.request.id,
        verification_code.user_id,
        verification_code.phone,
        result.get("provider"),
        result.get("sent"),
    )
    return result

