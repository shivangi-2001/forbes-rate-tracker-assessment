from django.urls import path
from .views import LatestRatesView, RateHistoryView, IngestRateView

urlpatterns = [
    path("rates/latest", LatestRatesView.as_view(), name="rates-latest"),
    path("rates/history", RateHistoryView.as_view(), name="rates-history"),
    path("rates/ingest", IngestRateView.as_view(), name="rates-ingest"),
]
