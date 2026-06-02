from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.contrib.auth import get_user_model

from apps.users.auth.email_confirmation import send_email_confirmation


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
