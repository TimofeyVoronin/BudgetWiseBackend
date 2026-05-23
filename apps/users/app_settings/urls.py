from django.urls import path

from apps.users.app_settings.views import AppSettingsMetaView, AppSettingsResetView, AppSettingsView


urlpatterns = [
    path("", AppSettingsView.as_view(), name="app-settings"),
    path("meta/", AppSettingsMetaView.as_view(), name="app-settings-meta"),
    path("reset/", AppSettingsResetView.as_view(), name="app-settings-reset"),
]
