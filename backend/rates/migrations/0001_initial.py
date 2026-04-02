from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Rate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("provider_name", models.CharField(max_length=255)),
                ("rate_type", models.CharField(max_length=100)),
                (
                    "rate_value",
                    models.DecimalField(decimal_places=6, max_digits=10),
                ),
                ("effective_date", models.DateField()),
                ("ingestion_timestamp", models.DateTimeField(auto_now_add=True)),
                ("raw_payload", models.JSONField(blank=True, null=True)),
            ],
            options={
                "indexes": [],
            },
        ),
        migrations.AlterUniqueTogether(
            name="rate",
            unique_together={("provider_name", "rate_type", "effective_date")},
        ),
        migrations.AddIndex(
            model_name="rate",
            index=models.Index(
                fields=["provider_name", "rate_type", "-effective_date"],
                name="idx_provider_type_date",
            ),
        ),
        migrations.AddIndex(
            model_name="rate",
            index=models.Index(
                fields=["rate_type", "effective_date"],
                name="idx_rate_type_date",
            ),
        ),
        migrations.AddIndex(
            model_name="rate",
            index=models.Index(
                fields=["ingestion_timestamp"],
                name="idx_ingestion_ts",
            ),
        ),
    ]
