from django.urls import path

from apps.pwa.background_sync.views import PwaBackgroundSyncMetaView
from apps.pwa.notification_settings.views import PwaNotificationSettingsView
from apps.pwa.push.views import (
    PwaMetaView,
    PwaPushSubscriptionDetailView,
    PwaPushSubscriptionListCreateView,
    PwaPushSubscriptionTestView,
)


app_name = "pwa"

urlpatterns = [
    path("meta/", PwaMetaView.as_view(), name="meta"),
    path(
        "background-sync/meta/",
        PwaBackgroundSyncMetaView.as_view(),
        name="background-sync-meta",
    ),
    path(
        "push-subscriptions/",
        PwaPushSubscriptionListCreateView.as_view(),
        name="push-subscription-list",
    ),
    path(
        "push-subscriptions/<int:pk>/",
        PwaPushSubscriptionDetailView.as_view(),
        name="push-subscription-detail",
    ),
    path(
        "push-subscriptions/<int:pk>/test/",
        PwaPushSubscriptionTestView.as_view(),
        name="push-subscription-test",
    ),
    path(
        "notification-settings/",
        PwaNotificationSettingsView.as_view(),
        name="notification-settings",
    ),
]
