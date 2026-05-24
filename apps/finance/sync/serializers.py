import re

from rest_framework import serializers


SYNC_CLIENT_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


class SyncResourceChangesSerializer(serializers.Serializer):
    upserted = serializers.ListField(child=serializers.DictField(), default=list)
    deleted = serializers.ListField(child=serializers.DictField(), default=list)


class SyncDomainAreaSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    resources = serializers.ListField(child=serializers.CharField())
    snapshots = serializers.ListField(child=serializers.CharField())
    actions = serializers.ListField(child=serializers.CharField())
    syncMode = serializers.CharField()
    priority = serializers.IntegerField()
    dependencies = serializers.ListField(child=serializers.CharField())
    conflictPolicy = serializers.CharField()
    notes = serializers.ListField(child=serializers.CharField())




class SyncVersioningSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    serverTime = serializers.DateTimeField()
    strategy = serializers.CharField()
    serverVersionField = serializers.CharField()
    syncTokenFormat = serializers.CharField()
    entityVersionFormat = serializers.CharField()
    etagFormat = serializers.CharField()
    clientRecordFields = serializers.DictField(child=serializers.CharField())
    operationFields = serializers.DictField(child=serializers.CharField())
    conflictDetection = serializers.DictField()
    tombstones = serializers.DictField()
    vectorClocks = serializers.DictField()
    writableResources = serializers.ListField(child=serializers.CharField())
    readOnlySnapshots = serializers.ListField(child=serializers.CharField())


class SyncMetaSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    serverTime = serializers.DateTimeField()
    supportedResources = serializers.ListField(child=serializers.CharField())
    writableResources = serializers.ListField(child=serializers.CharField(), required=False)
    readOnlyResources = serializers.ListField(child=serializers.CharField(), required=False)
    readOnlySnapshots = serializers.ListField(child=serializers.CharField())
    excludedResources = serializers.ListField(child=serializers.CharField(), required=False)
    domainAreas = SyncDomainAreaSerializer(many=True, required=False)
    outOfScope = SyncDomainAreaSerializer(many=True, required=False)
    supportedActions = serializers.ListField(child=serializers.CharField())
    conflictStrategies = serializers.ListField(child=serializers.CharField(), required=False)
    versioning = serializers.DictField(required=False)
    maxBatchSize = serializers.IntegerField()


class SyncDomainsSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    serverTime = serializers.DateTimeField()
    supportedResources = serializers.ListField(child=serializers.CharField())
    writableResources = serializers.ListField(child=serializers.CharField())
    readOnlyResources = serializers.ListField(child=serializers.CharField())
    readOnlySnapshots = serializers.ListField(child=serializers.CharField())
    excludedResources = serializers.ListField(child=serializers.CharField())
    domainAreas = SyncDomainAreaSerializer(many=True)
    outOfScope = SyncDomainAreaSerializer(many=True)


class SyncBootstrapSerializer(serializers.Serializer):
    serverTime = serializers.DateTimeField()
    syncToken = serializers.DateTimeField()
    resources = serializers.DictField(child=serializers.ListField(child=serializers.DictField()))
    snapshots = serializers.DictField(child=serializers.DictField(), required=False)


class SyncPullSerializer(serializers.Serializer):
    serverTime = serializers.DateTimeField()
    syncToken = serializers.DateTimeField()
    changes = serializers.DictField(child=SyncResourceChangesSerializer())
    snapshots = serializers.DictField(child=serializers.DictField(), required=False)


class SyncPushOperationSerializer(serializers.Serializer):
    clientMutationId = serializers.CharField(max_length=150, trim_whitespace=True)
    resource = serializers.CharField(max_length=60, trim_whitespace=True)
    action = serializers.ChoiceField(choices=["create", "update", "delete"])
    clientId = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True, trim_whitespace=True)
    serverId = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    clientUpdatedAt = serializers.DateTimeField(required=False, allow_null=True)
    baseVersion = serializers.DateTimeField(required=False, allow_null=True)
    payload = serializers.DictField(required=False, default=dict)


class SyncPushRequestSerializer(serializers.Serializer):
    clientId = serializers.CharField(max_length=100, trim_whitespace=True)
    deviceId = serializers.CharField(max_length=150, trim_whitespace=True)
    baseSyncToken = serializers.DateTimeField(required=False, allow_null=True)
    operations = SyncPushOperationSerializer(many=True)

    def validate_clientId(self, value: str) -> str:
        return self._validate_client_identifier(value, field_name="clientId")

    def validate_deviceId(self, value: str) -> str:
        return self._validate_client_identifier(value, field_name="deviceId")

    def _validate_client_identifier(self, value: str, *, field_name: str) -> str:
        if not value:
            raise serializers.ValidationError("Значение обязательно.")

        if not SYNC_CLIENT_IDENTIFIER_PATTERN.fullmatch(value):
            raise serializers.ValidationError(
                "Допустимы только латинские буквы, цифры, точка, подчёркивание, двоеточие и дефис."
            )

        return value

    def validate_operations(self, value):
        max_batch_size = self.context.get("max_batch_size", 100)

        if not value:
            raise serializers.ValidationError("Batch синхронизации должен содержать хотя бы одну операцию.")

        if len(value) > max_batch_size:
            raise serializers.ValidationError(
                f"В одном запросе синхронизации можно передать не более {max_batch_size} операций."
            )

        mutation_ids = [item["clientMutationId"] for item in value]
        duplicate_ids = sorted(
            mutation_id
            for mutation_id in set(mutation_ids)
            if mutation_ids.count(mutation_id) > 1
        )

        if duplicate_ids:
            raise serializers.ValidationError(
                f"В batch-запросе повторяются clientMutationId: {', '.join(duplicate_ids)}."
            )

        return value


class SyncPushResultSerializer(serializers.Serializer):
    clientMutationId = serializers.CharField()
    resource = serializers.CharField()
    action = serializers.CharField()
    status = serializers.CharField()
    clientId = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    serverId = serializers.IntegerField(allow_null=True, required=False)
    version = serializers.DateTimeField(allow_null=True, required=False)
    serverVersion = serializers.CharField(allow_blank=True, allow_null=True, required=False)
    data = serializers.DictField(required=False)
    error = serializers.DictField(required=False)


class SyncPushResponseSerializer(serializers.Serializer):
    serverTime = serializers.DateTimeField()
    syncToken = serializers.DateTimeField()
    results = SyncPushResultSerializer(many=True)


class SyncConflictFieldSerializer(serializers.Serializer):
    field = serializers.CharField()
    serverField = serializers.CharField()
    clientValue = serializers.JSONField(allow_null=True)
    serverValue = serializers.JSONField(allow_null=True)


class SyncConflictDataSerializer(serializers.Serializer):
    clientData = serializers.DictField()
    serverData = serializers.DictField()
    baseVersion = serializers.DateTimeField(allow_null=True, required=False)
    serverVersion = serializers.DateTimeField(allow_null=True, required=False)
    conflictFields = SyncConflictFieldSerializer(many=True)
    availableStrategies = serializers.ListField(child=serializers.CharField())


class SyncConflictResolveRequestSerializer(serializers.Serializer):
    resource = serializers.CharField(max_length=60, trim_whitespace=True)
    serverId = serializers.IntegerField(min_value=1)
    strategy = serializers.ChoiceField(choices=["server_wins", "client_wins", "merge"])
    payload = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        strategy = attrs.get("strategy")
        payload = attrs.get("payload") or {}
        if strategy in {"client_wins", "merge"} and not payload:
            raise serializers.ValidationError({"payload": "Для client_wins и merge нужно передать payload."})
        return attrs


class SyncConflictResolveResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    resource = serializers.CharField()
    serverId = serializers.IntegerField()
    strategy = serializers.CharField()
    version = serializers.DateTimeField(allow_null=True, required=False)
    data = serializers.DictField()


class SyncOperationLogItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    clientId = serializers.CharField()
    deviceId = serializers.CharField()
    clientMutationId = serializers.CharField()
    resource = serializers.CharField()
    action = serializers.CharField()
    status = serializers.CharField()
    serverId = serializers.IntegerField(allow_null=True)
    requestHash = serializers.CharField(allow_blank=True)
    hasError = serializers.BooleanField()
    errorCode = serializers.CharField(allow_blank=True, allow_null=True)
    errorMessage = serializers.CharField(allow_blank=True, allow_null=True)
    createdAt = serializers.DateTimeField()
    updatedAt = serializers.DateTimeField()
    responseData = serializers.DictField(required=False)
    errorData = serializers.DictField(required=False)


class SyncOperationsLogResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pageSize = serializers.IntegerField()
    hasNext = serializers.BooleanField()
    hasPrevious = serializers.BooleanField()
    results = SyncOperationLogItemSerializer(many=True)


class SyncStatusOperationStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    applied = serializers.IntegerField()
    duplicate = serializers.IntegerField()
    failed = serializers.IntegerField()
    conflict = serializers.IntegerField()
    skipped = serializers.IntegerField()


class SyncStatusSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    serverTime = serializers.DateTimeField()
    syncToken = serializers.DateTimeField()
    lastOperationAt = serializers.DateTimeField(allow_null=True)
    operations = SyncStatusOperationStatsSerializer()
    pendingConflictsCount = serializers.IntegerField()
    supportedResources = serializers.ListField(child=serializers.CharField())
    writableResources = serializers.ListField(child=serializers.CharField())
    readOnlyResources = serializers.ListField(child=serializers.CharField())
    readOnlySnapshots = serializers.ListField(child=serializers.CharField())
    supportedActions = serializers.ListField(child=serializers.CharField())
    maxBatchSize = serializers.IntegerField()
    lastOperations = SyncOperationLogItemSerializer(many=True)
