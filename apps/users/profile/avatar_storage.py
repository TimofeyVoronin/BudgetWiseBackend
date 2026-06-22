from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpRequest

logger = logging.getLogger("apps")


@dataclass(frozen=True)
class AvatarUpdateResult:
    avatar_url: str | None
    old_reference: str
    new_reference: str


def get_avatar_storage_provider() -> str:
    return str(getattr(settings, "AVATAR_STORAGE_PROVIDER", "local") or "local").strip().lower()


def get_user_avatar_url(user, request: HttpRequest | None = None) -> str | None:
    avatar_url = str(getattr(user, "avatar_url", "") or "").strip()
    if avatar_url:
        return avatar_url

    if not getattr(user, "avatar", None):
        return None

    try:
        local_avatar_url = user.avatar.url
    except ValueError:
        return None

    if request is not None:
        return request.build_absolute_uri(local_avatar_url)

    return local_avatar_url


def upload_user_avatar(*, user, uploaded_file) -> AvatarUpdateResult:
    provider = get_avatar_storage_provider()

    if provider == "cloudinary":
        return _upload_user_avatar_to_cloudinary(user=user, uploaded_file=uploaded_file)

    if provider == "local":
        return _upload_user_avatar_to_local_storage(user=user, uploaded_file=uploaded_file)

    raise ValueError(f"Unsupported avatar storage provider: {provider}")


def delete_user_avatar(*, user) -> AvatarUpdateResult:
    old_reference = _get_avatar_reference(user)
    old_avatar_name = user.avatar.name if getattr(user, "avatar", None) else ""
    old_public_id = str(getattr(user, "avatar_public_id", "") or "").strip()

    if not old_reference:
        return AvatarUpdateResult(avatar_url=None, old_reference="", new_reference="")

    user.avatar = None
    user.avatar_url = ""
    user.avatar_public_id = ""
    user.save(update_fields=["avatar", "avatar_url", "avatar_public_id"])

    _delete_local_avatar_if_unused(old_avatar_name, "")
    _delete_cloudinary_avatar(old_public_id)

    return AvatarUpdateResult(
        avatar_url=None,
        old_reference=old_reference,
        new_reference="",
    )


def _upload_user_avatar_to_local_storage(*, user, uploaded_file) -> AvatarUpdateResult:
    old_reference = _get_avatar_reference(user)
    old_avatar_name = user.avatar.name if getattr(user, "avatar", None) else ""
    old_public_id = str(getattr(user, "avatar_public_id", "") or "").strip()

    user.avatar = uploaded_file
    user.avatar_url = ""
    user.avatar_public_id = ""
    user.save(update_fields=["avatar", "avatar_url", "avatar_public_id"])

    _delete_local_avatar_if_unused(old_avatar_name, user.avatar.name)
    _delete_cloudinary_avatar(old_public_id)

    return AvatarUpdateResult(
        avatar_url=get_user_avatar_url(user),
        old_reference=old_reference,
        new_reference=user.avatar.name,
    )


def _upload_user_avatar_to_cloudinary(*, user, uploaded_file) -> AvatarUpdateResult:
    old_reference = _get_avatar_reference(user)
    old_avatar_name = user.avatar.name if getattr(user, "avatar", None) else ""
    old_public_id = str(getattr(user, "avatar_public_id", "") or "").strip()

    upload_result = _cloudinary_upload(user=user, uploaded_file=uploaded_file)
    new_avatar_url = str(upload_result.get("secure_url") or upload_result.get("url") or "").strip()
    new_public_id = str(upload_result.get("public_id") or "").strip()

    if not new_avatar_url or not new_public_id:
        raise RuntimeError("Cloudinary avatar upload did not return secure_url and public_id.")

    user.avatar = None
    user.avatar_url = new_avatar_url
    user.avatar_public_id = new_public_id
    user.save(update_fields=["avatar", "avatar_url", "avatar_public_id"])

    _delete_local_avatar_if_unused(old_avatar_name, "")
    _delete_cloudinary_avatar(old_public_id, keep_public_id=new_public_id)

    return AvatarUpdateResult(
        avatar_url=new_avatar_url,
        old_reference=old_reference,
        new_reference=new_public_id,
    )


def _cloudinary_upload(*, user, uploaded_file) -> dict[str, Any]:
    _configure_cloudinary()

    import cloudinary.uploader

    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass

    folder = str(getattr(settings, "CLOUDINARY_AVATAR_FOLDER", "budgetwise/avatars") or "budgetwise/avatars").strip("/")
    public_id = f"user_{user.pk}_{uuid.uuid4().hex}"

    return cloudinary.uploader.upload(
        uploaded_file,
        folder=folder,
        public_id=public_id,
        resource_type="image",
        allowed_formats=["jpg", "jpeg", "png", "webp"],
        overwrite=False,
        invalidate=True,
    )


def _delete_cloudinary_avatar(public_id: str, *, keep_public_id: str = "") -> None:
    public_id = str(public_id or "").strip()
    keep_public_id = str(keep_public_id or "").strip()

    if not public_id or public_id == keep_public_id:
        return

    try:
        _configure_cloudinary()
        import cloudinary.uploader

        cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    except Exception:
        logger.exception(
            "Cloudinary avatar delete failed.",
            extra={"avatar_public_id": public_id},
        )


def _configure_cloudinary() -> None:
    cloud_name = str(getattr(settings, "CLOUDINARY_CLOUD_NAME", "") or "").strip()
    api_key = str(getattr(settings, "CLOUDINARY_API_KEY", "") or "").strip()
    api_secret = str(getattr(settings, "CLOUDINARY_API_SECRET", "") or "").strip()

    if not cloud_name or not api_key or not api_secret:
        raise RuntimeError("Cloudinary credentials are not configured.")

    import cloudinary

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def _delete_local_avatar_if_unused(file_name: str, current_file_name: str) -> None:
    if not file_name or file_name == current_file_name:
        return

    if default_storage.exists(file_name):
        default_storage.delete(file_name)


def _get_avatar_reference(user) -> str:
    public_id = str(getattr(user, "avatar_public_id", "") or "").strip()
    if public_id:
        return public_id

    if getattr(user, "avatar", None):
        return user.avatar.name or ""

    return ""
