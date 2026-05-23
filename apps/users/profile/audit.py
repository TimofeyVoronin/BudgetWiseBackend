from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest

from apps.users.models import User, UserProfileAuditAction, UserProfileAuditLog

logger = logging.getLogger("apps")

PROFILE_AUDIT_FIELD_MAP = {
    "first_name": "firstName",
    "last_name": "lastName",
    "middle_name": "middleName",
    "phone": "phone",
    "city": "city",
    "bio": "bio",
}
NAME_AUDIT_FIELDS = {"firstName", "lastName", "middleName"}


def get_profile_audit_snapshot(user: User) -> dict[str, Any]:
    """Return profile fields in the same naming style as the public profile API."""

    return {
        public_name: getattr(user, model_name, "") or ""
        for model_name, public_name in PROFILE_AUDIT_FIELD_MAP.items()
    }


def log_profile_update_audit(
    *,
    user: User,
    old_values: dict[str, Any],
    new_values: dict[str, Any],
    request: HttpRequest | None = None,
) -> list[UserProfileAuditLog]:
    changed_fields = [
        field_name
        for field_name in PROFILE_AUDIT_FIELD_MAP.values()
        if old_values.get(field_name) != new_values.get(field_name)
    ]

    if not changed_fields:
        return []

    old_changed_values = {field: old_values.get(field) for field in changed_fields}
    new_changed_values = {field: new_values.get(field) for field in changed_fields}
    metadata = {"source": "profile_api"}

    logs = [
        log_profile_audit_event(
            user=user,
            action=UserProfileAuditAction.PROFILE_UPDATED,
            changed_fields=changed_fields,
            old_values=old_changed_values,
            new_values=new_changed_values,
            metadata=metadata,
            request=request,
        )
    ]

    if NAME_AUDIT_FIELDS.intersection(changed_fields):
        name_fields = [field for field in changed_fields if field in NAME_AUDIT_FIELDS]
        logs.append(
            log_profile_audit_event(
                user=user,
                action=UserProfileAuditAction.NAME_CHANGED,
                changed_fields=name_fields,
                old_values={field: old_changed_values.get(field) for field in name_fields},
                new_values={field: new_changed_values.get(field) for field in name_fields},
                metadata=metadata,
                request=request,
            )
        )

    simple_actions = {
        "phone": UserProfileAuditAction.PHONE_CHANGED,
        "city": UserProfileAuditAction.CITY_CHANGED,
        "bio": UserProfileAuditAction.BIO_CHANGED,
    }
    for field_name, action in simple_actions.items():
        if field_name in changed_fields:
            logs.append(
                log_profile_audit_event(
                    user=user,
                    action=action,
                    changed_fields=[field_name],
                    old_values={field_name: old_changed_values.get(field_name)},
                    new_values={field_name: new_changed_values.get(field_name)},
                    metadata=metadata,
                    request=request,
                )
            )

    return logs


def log_profile_avatar_audit(
    *,
    user: User,
    action: str,
    old_avatar_name: str = "",
    new_avatar_name: str = "",
    request: HttpRequest | None = None,
) -> UserProfileAuditLog:
    return log_profile_audit_event(
        user=user,
        action=action,
        changed_fields=["avatar"],
        old_values={"avatar": old_avatar_name or None},
        new_values={"avatar": new_avatar_name or None},
        metadata={"source": "profile_avatar_api"},
        request=request,
    )


def log_profile_audit_event(
    *,
    user: User,
    action: str,
    changed_fields: list[str] | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> UserProfileAuditLog:
    audit_log = UserProfileAuditLog.objects.create(
        user=user,
        action=action,
        changed_fields=changed_fields or [],
        old_values=old_values or {},
        new_values=new_values or {},
        metadata=metadata or {},
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )

    logger.info(
        "User profile audit event recorded.",
        extra={
            "user_id": user.id,
            "action": action,
            "changed_fields": audit_log.changed_fields,
            "ip_address": audit_log.ip_address,
        },
    )
    return audit_log


def _get_client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None

    return request.META.get("REMOTE_ADDR") or None


def _get_user_agent(request: HttpRequest | None) -> str:
    if request is None:
        return ""

    return (request.META.get("HTTP_USER_AGENT") or "")[:1000]
