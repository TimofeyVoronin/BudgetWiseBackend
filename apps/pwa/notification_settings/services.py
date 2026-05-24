from apps.pwa.models import PwaNotificationSettings


def get_or_create_pwa_notification_settings(*, user) -> PwaNotificationSettings:
    settings, _ = PwaNotificationSettings.objects.get_or_create(user=user)
    return settings
