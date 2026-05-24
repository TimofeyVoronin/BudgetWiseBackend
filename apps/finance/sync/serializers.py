from rest_framework import serializers


class SyncResourceChangesSerializer(serializers.Serializer):
    upserted = serializers.ListField(child=serializers.DictField(), default=list)
    deleted = serializers.ListField(child=serializers.DictField(), default=list)


class SyncMetaSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    serverTime = serializers.DateTimeField()
    supportedResources = serializers.ListField(child=serializers.CharField())
    readOnlySnapshots = serializers.ListField(child=serializers.CharField())
    supportedActions = serializers.ListField(child=serializers.CharField())
    maxBatchSize = serializers.IntegerField()


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
    clientMutationId = serializers.CharField(max_length=150)
    resource = serializers.CharField(max_length=60)
    action = serializers.ChoiceField(choices=["create", "update", "delete"])
    clientId = serializers.CharField(max_length=150, required=False, allow_blank=True, allow_null=True)
    serverId = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    clientUpdatedAt = serializers.DateTimeField(required=False, allow_null=True)
    baseVersion = serializers.DateTimeField(required=False, allow_null=True)
    payload = serializers.DictField(required=False, default=dict)


class SyncPushRequestSerializer(serializers.Serializer):
    clientId = serializers.CharField(max_length=100)
    deviceId = serializers.CharField(max_length=150)
    baseSyncToken = serializers.DateTimeField(required=False, allow_null=True)
    operations = SyncPushOperationSerializer(many=True)

    def validate_operations(self, value):
        max_batch_size = self.context.get("max_batch_size", 100)

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
    data = serializers.DictField(required=False)
    error = serializers.DictField(required=False)


class SyncPushResponseSerializer(serializers.Serializer):
    serverTime = serializers.DateTimeField()
    syncToken = serializers.DateTimeField()
    results = SyncPushResultSerializer(many=True)
