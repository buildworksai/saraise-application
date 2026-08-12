"""Prometheus metrics endpoint."""

from django.http import HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def metrics(request):
    """Expose Prometheus metrics in text format.

    This endpoint only serves GET/HEAD scrape traffic. Django's CSRF middleware
    does not require a CSRF token for safe methods, so an explicit exemption is
    unnecessary.
    """
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
