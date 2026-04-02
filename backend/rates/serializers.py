from rest_framework import serializers
from .models import Rate


class RateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rate
        fields = [
            "id",
            "provider_name",
            "rate_type",
            "rate_value",
            "effective_date",
            "ingestion_timestamp",
        ]


class RateIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rate
        fields = ["provider_name", "rate_type", "rate_value", "effective_date"]
        validators = []

    def validate_rate_value(self, value):
        if value is None:
            raise serializers.ValidationError("rate_value cannot be null.")
        if value < 0:
            raise serializers.ValidationError("rate_value must be non-negative.")
        return value

    def validate_provider_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("provider_name cannot be blank.")
        return value.strip()
