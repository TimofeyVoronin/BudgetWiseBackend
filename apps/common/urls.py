from django.urls import path

from apps.common.monitoring.health_views import health_check
from apps.common.monitoring.metrics_views import metrics_view

urlpatterns = [
    path("health/", health_check, name="health"),
    path("metrics/", metrics_view, name="metrics"),
]
