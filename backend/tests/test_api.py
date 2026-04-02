import pytest
from rest_framework.test import APIClient
from rates.models import Rate
from django.core.cache import cache
 
 
@pytest.fixture
def client():
    return APIClient()

@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()
 
 
# ── /rates/latest ──────────────────────────────────────────────────────────────
class TestLatestRates:
    def test_returns_200_no_auth(self, client, sample_rate):
        response = client.get("/api/rates/latest")
        assert response.status_code == 200

    def test_returns_list(self, client, sample_rate, another_rate):
        response = client.get("/api/rates/latest")
        assert response.status_code == 200
        data = response.json()
        
        # Check that we got the paginated dictionary
        assert isinstance(data, dict)
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) >= 2

    def test_filter_by_type(self, client, sample_rate, another_rate):
        response = client.get("/api/rates/latest?type=mortgage_30yr")
        data = response.json()
        
        # Iterate over the nested 'results' list
        results = data["results"]
        assert all(r["rate_type"] == "mortgage_30yr" for r in results)

    def test_latest_returns_most_recent(self, db, client):
        Rate.objects.create(
            provider_name="BankA", rate_type="mortgage_30yr",
            rate_value="6.5", effective_date="2024-01-01",
        )
        Rate.objects.create(
            provider_name="BankA", rate_type="mortgage_30yr",
            size_value="6.9", effective_date="2024-06-01",
        )
        response = client.get("/api/rates/latest")
        data = response.json()
        
        # Look inside data["results"] for the actual objects
        bank_a_list = [r for r in data["results"] if r["provider_name"] == "BankA"]
        
        assert len(bank_a_list) > 0, "BankA not found in response results"
        assert bank_a_list[0]["effective_date"] == "2024-06-01"
        
        
# ── /rates/history ─────────────────────────────────────────────────────────────
 
class TestRateHistory:
    def test_requires_provider_and_type(self, client):
        response = client.get("/api/rates/history")
        assert response.status_code == 400
        assert "error" in response.json()
 
    def test_returns_paginated_results(self, client, sample_rate):
        response = client.get(
            "/api/rates/history?provider=TestBank&type=mortgage_30yr"
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "count" in data
 
    def test_date_filters_work(self, db, client):
        Rate.objects.create(
            provider_name="BankA", rate_type="savings_1yr",
            rate_value="4.0", effective_date="2024-01-15",
        )
        Rate.objects.create(
            provider_name="BankA", rate_type="savings_1yr",
            rate_value="4.1", effective_date="2024-02-15",
        )
        Rate.objects.create(
            provider_name="BankA", rate_type="savings_1yr",
            rate_value="4.2", effective_date="2024-03-15",
        )
        response = client.get(
            "/api/rates/history?provider=BankA&type=savings_1yr"
            "&from=2024-02-01&to=2024-02-28"
        )
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["effective_date"] == "2024-02-15"
 
    def test_invalid_date_returns_400(self, client, sample_rate):
        response = client.get(
            "/api/rates/history?provider=TestBank&type=mortgage_30yr&from=not-a-date"
        )
        assert response.status_code == 400
 
 
# ── /rates/ingest ──────────────────────────────────────────────────────────────
 
class TestIngestRate:
    VALID_PAYLOAD = {
        "provider_name": "NewBank",
        "rate_type": "mortgage_15yr",
        "rate_value": "5.250000",
        "effective_date": "2024-07-01",
    }
 
    def test_rejects_unauthenticated(self, client):
        response = client.post("/api/rates/ingest", self.VALID_PAYLOAD, format="json")
        assert response.status_code == 403
 
    def test_rejects_wrong_token(self, client, api_key):
        client.credentials(HTTP_AUTHORIZATION="Bearer wrong-token")
        response = client.post("/api/rates/ingest", self.VALID_PAYLOAD, format="json")
        assert response.status_code == 403
 
    def test_creates_rate_with_valid_token(self, client, api_key, db):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = client.post("/api/rates/ingest", self.VALID_PAYLOAD, format="json")
        assert response.status_code == 201
        assert Rate.objects.filter(provider_name="NewBank").exists()
 
    def test_idempotent_second_post_returns_200(self, client, api_key, db):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        client.post("/api/rates/ingest", self.VALID_PAYLOAD, format="json")
        response = client.post("/api/rates/ingest", self.VALID_PAYLOAD, format="json")
        assert response.status_code == 200
        assert Rate.objects.filter(provider_name="NewBank").count() == 1
 
    def test_rejects_missing_fields(self, client, api_key, db):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        response = client.post(
            "/api/rates/ingest",
            {"provider_name": "X"},
            format="json",
        )
        assert response.status_code == 422
        assert "errors" in response.json()
 
    def test_rejects_negative_rate(self, client, api_key, db):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {api_key}")
        payload = {**self.VALID_PAYLOAD, "rate_value": "-1.0"}
        response = client.post("/api/rates/ingest", payload, format="json")
        assert response.status_code == 422
        
