from django.db import models


class Rate(models.Model):
    provider_name = models.CharField(max_length=255)
    rate_type = models.CharField(max_length=100)
    rate_value = models.DecimalField(max_digits=10, decimal_places=6)
    effective_date = models.DateField()
    ingestion_timestamp = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField(null=True, blank=True)

    class Meta:
        # Unique constraint enables idempotent upsert
        unique_together = ("provider_name", "rate_type", "effective_date")
        indexes = [
            # Latest rate per provider query
            models.Index(
                fields=["provider_name", "rate_type", "-effective_date"],
                name="idx_provider_type_date",
            ),
            # Rate change over 30 days for a given type
            models.Index(
                fields=["rate_type", "effective_date"],
                name="idx_rate_type_date",
            ),
            # All records ingested in a 24-hour window
            models.Index(
                fields=["ingestion_timestamp"],
                name="idx_ingestion_ts",
            ),
        ]

    def __str__(self):
        return f"{self.provider_name} | {self.rate_type} | {self.effective_date} | {self.rate_value}"
