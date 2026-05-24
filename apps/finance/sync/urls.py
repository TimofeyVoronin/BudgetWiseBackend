from django.urls import path

from apps.finance.sync.views import (
    SyncBootstrapView,
    SyncConflictResolveView,
    SyncDomainsView,
    SyncMetaView,
    SyncPullView,
    SyncPushView,
)


urlpatterns = [
    path("meta/", SyncMetaView.as_view(), name="sync-meta"),
    path("domains/", SyncDomainsView.as_view(), name="sync-domains"),
    path("bootstrap/", SyncBootstrapView.as_view(), name="sync-bootstrap"),
    path("pull/", SyncPullView.as_view(), name="sync-pull"),
    path("push/", SyncPushView.as_view(), name="sync-push"),
    path("conflicts/resolve/", SyncConflictResolveView.as_view(), name="sync-conflict-resolve"),
]
