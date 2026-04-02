import pytest
from rates.models import Rate


@pytest.fixture
def sample_rate(db):
    return Rate.objects.create(
        provider_name="TestBank",
        rate_type="mortgage_30yr",
        rate_value="6.750000",
        effective_date="2024-03-01",
        raw_payload={"provider_name": "TestBank", "rate_type": "mortgage_30yr",
                     "rate_value": 6.75, "effective_date": "2024-03-01"},
    )


@pytest.fixture
def another_rate(db):
    return Rate.objects.create(
        provider_name="SavingsPlus",
        rate_type="savings_1yr",
        rate_value="4.200000",
        effective_date="2024-03-01",
    )


@pytest.fixture
def api_key(settings):
    settings.INGEST_API_KEY = "test-secret-key-123"
    return "test-secret-key-123"
