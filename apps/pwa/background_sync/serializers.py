from rest_framework import serializers


class PwaBackgroundSyncMetaSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    syncEndpoint = serializers.CharField()
    pullEndpoint = serializers.CharField()
    statusEndpoint = serializers.CharField()
    operationsEndpoint = serializers.CharField()
    recommendedRetrySeconds = serializers.IntegerField()
    maxBatchSize = serializers.IntegerField()
