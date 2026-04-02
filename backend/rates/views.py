import logging

from django.core.cache import cache
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .models import Rate
from .serializers import RateIngestSerializer, RateSerializer


logger = logging.getLogger("rates")

LATEST_CACHE_KEY = "rates:latest:{rate_type}"
LATEST_CACHE_TTL = 300  # 5 minutes


def _latest_cache_key(rate_type=None):
    return LATEST_CACHE_KEY.format(rate_type=rate_type or "all")



class RatePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        """
        Customized to match your desired response structure 
        while adding standard 'next' and 'previous' links.
        """
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })
        
class LatestRatesView(APIView):
    permission_classes = [AllowAny]
    pagination_class = RatePagination

    def get(self, request):
        rate_type = request.query_params.get("type")
        
        # Determine if this is a default, unpaginated request for caching
        is_default_request = not any(k in request.query_params for k in ["page", "page_size"])
        cache_key = _latest_cache_key(rate_type)

        if is_default_request:
            cached = cache.get(cache_key)
            if cached:
                return Response(cached)

        # Query Logic
        qs = Rate.objects.all().order_by("provider_name", "rate_type", "-effective_date")
        if rate_type:
            qs = qs.filter(rate_type=rate_type)
        
        # PostgreSQL distinct optimization
        qs = qs.distinct("provider_name", "rate_type")

        # Execute Pagination
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        
        serializer = RateSerializer(page, many=True)
        response_obj = paginator.get_paginated_response(serializer.data)

        # Cache only the result of the default request
        if is_default_request:
            cache.set(cache_key, response_obj.data, LATEST_CACHE_TTL)

        return response_obj

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