"""Prometheus metrics endpoint."""

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


@csrf_exempt
def metrics(request):
    """Expose Prometheus metrics in text format.

    This endpoint is exempt from CSRF protection to allow Prometheus scraping.
    Metrics endpoints are typically accessed by monitoring systems without
    authentication tokens or CSRF tokens.
    """
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
