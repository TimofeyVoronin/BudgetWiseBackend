from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users.admin_api.views import UserViewSet
from apps.users.profile.views import CurrentUserView


app_name = "users"

router = DefaultRouter()
router.register("", UserViewSet, basename="user")

urlpatterns = [
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("", include(router.urls)),
]
