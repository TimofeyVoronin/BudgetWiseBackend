from django.urls import path

from apps.users.profile.views import UserProfileAvatarView, UserProfileMeView


urlpatterns = [
    path("me/", UserProfileMeView.as_view(), name="profile-me"),
    path("me/avatar/", UserProfileAvatarView.as_view(), name="profile-me-avatar"),
]
