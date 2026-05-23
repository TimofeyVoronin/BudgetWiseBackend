from django.urls import include, path

from apps.common.api_root_views import APIRootView
from apps.users.app_settings_views import AppSettingsMetaView, AppSettingsResetView, AppSettingsView
from apps.users.profile_views import HomeGreetingView, UserProfileAvatarView, UserProfileMeView


urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("auth/", include("apps.users.auth_urls")),
    path("me/", HomeGreetingView.as_view(), name="home-greeting"),
    path("profile/me/", UserProfileMeView.as_view(), name="profile-me"),
    path("profile/me/avatar/", UserProfileAvatarView.as_view(), name="profile-me-avatar"),
    path("settings/app/", AppSettingsView.as_view(), name="app-settings"),
    path("settings/app/meta/", AppSettingsMetaView.as_view(), name="app-settings-meta"),
    path("settings/app/reset/", AppSettingsResetView.as_view(), name="app-settings-reset"),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]
