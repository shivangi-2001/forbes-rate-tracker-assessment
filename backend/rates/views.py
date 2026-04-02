import logging
import time

from django.core.cache import cache
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Rate
from .serializers import RateIngestSerializer, RateSerializer

logger = logging.getLogger("rates")

LATEST_CACHE_KEY = "rates:latest:{rate_type}"
LATEST_CACHE_TTL = 300  # 5 minutes


def _latest_cache_key(rate_type=None):
    return LATEST_CACHE_KEY.format(rate_type=rate_type or "all")


class LatestRatesView(APIView):
    permission_classes = [AllowAny]

    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100

    def get(self, request):
        rate_type = request.query_params.get("type")

        # Pagination params — only cache unpaginated requests
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(
                self.MAX_PAGE_SIZE,
                max(1, int(request.query_params.get("page_size", self.DEFAULT_PAGE_SIZE))),
            )
        except (ValueError, TypeError):
            page_size = self.DEFAULT_PAGE_SIZE

        is_paginated = "page" in request.query_params or "page_size" in request.query_params

        # Only use cache for unpaginated requests (page 1, default size)
        cache_key = _latest_cache_key(rate_type)
        if not is_paginated:
            cached = cache.get(cache_key)
            if cached is not None:
                logger.info("Cache hit", extra={"cache_key": cache_key})
                return Response(cached)

        t0 = time.monotonic()
        qs = Rate.objects.all()
        if rate_type:
            qs = qs.filter(rate_type=rate_type)

        # Latest rate per (provider, type) using distinct on effective_date desc
        qs = qs.order_by("provider_name", "rate_type", "-effective_date").distinct(
            "provider_name", "rate_type"
        )

        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > 200:
            logger.warning(
                "Slow query on /rates/latest",
                extra={"elapsed_ms": round(elapsed_ms, 2)},
            )

        # Apply pagination
        total_count = qs.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        page_qs = qs[offset: offset + page_size]

        data = RateSerializer(page_qs, many=True).data

        response_data = {
            "count": total_count,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "results": data,
        }

        # Cache only the first page / unpaginated response
        if not is_paginated:
            cache.set(cache_key, response_data, LATEST_CACHE_TTL)
            logger.info("Cache miss — stored", extra={"cache_key": cache_key})

        return Response(response_data)


class RateHistoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        provider = request.query_params.get("provider")
        rate_type = request.query_params.get("type")
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")

        if not provider or not rate_type:
            return Response(
                {"error": "Both 'provider' and 'type' query params are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = Rate.objects.filter(
            provider_name=provider, rate_type=rate_type
        ).order_by("effective_date")

        if from_date:
            parsed = parse_date(from_date)
            if not parsed:
                return Response(
                    {"error": "Invalid 'from' date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(effective_date__gte=parsed)

        if to_date:
            parsed = parse_date(to_date)
            if not parsed:
                return Response(
                    {"error": "Invalid 'to' date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(effective_date__lte=parsed)

        paginator = self.pagination_class() if hasattr(self, "pagination_class") else None

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 50
        paginator.max_page_size = 200
        page = paginator.paginate_queryset(qs, request)
        serializer = RateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class IngestRateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RateIngestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        rate, created = Rate.objects.update_or_create(
            provider_name=serializer.validated_data["provider_name"],
            rate_type=serializer.validated_data["rate_type"],
            effective_date=serializer.validated_data["effective_date"],
            defaults={
                "rate_value": serializer.validated_data["rate_value"],
                "raw_payload": request.data,
            },
        )

        # Invalidate relevant cache keys
        for key in [_latest_cache_key(), _latest_cache_key(rate.rate_type)]:
            cache.delete(key)
        logger.info(
            "Rate ingested via webhook",
            extra={
                "provider": rate.provider_name,
                "rate_type": rate.rate_type,
                "was_created": created,
            },
        )

        return Response(
            RateSerializer(rate).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )