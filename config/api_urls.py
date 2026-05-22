from django.urls import include, path

from apps.common.api_root_views import APIRootView
from apps.users.profile_views import UserProfileMeView


urlpatterns = [
    path("", APIRootView.as_view(), name="api-root"),
    path("auth/", include("apps.users.auth_urls")),
    path("profile/me/", UserProfileMeView.as_view(), name="profile-me"),
    path("users/", include("apps.users.urls")),
    path("finance/", include("apps.finance.urls")),
]
