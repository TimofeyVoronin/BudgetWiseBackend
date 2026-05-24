from django.urls import path

from apps.finance.sync.views import (
    SyncBootstrapView,
    SyncConflictResolveView,
    SyncDomainsView,
    SyncMetaView,
    SyncOperationsLogView,
    SyncPullView,
    SyncStatusView,
    SyncPushView,
    SyncVersioningView,
)


urlpatterns = [
    path("meta/", SyncMetaView.as_view(), name="sync-meta"),
    path("domains/", SyncDomainsView.as_view(), name="sync-domains"),
    path("versioning/", SyncVersioningView.as_view(), name="sync-versioning"),
    path("status/", SyncStatusView.as_view(), name="sync-status"),
    path("operations/", SyncOperationsLogView.as_view(), name="sync-operations"),
    path("bootstrap/", SyncBootstrapView.as_view(), name="sync-bootstrap"),
    path("pull/", SyncPullView.as_view(), name="sync-pull"),
    path("push/", SyncPushView.as_view(), name="sync-push"),
    path("conflicts/resolve/", SyncConflictResolveView.as_view(), name="sync-conflict-resolve"),
]
