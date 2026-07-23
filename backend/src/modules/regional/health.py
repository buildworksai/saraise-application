"""Sanitized public liveness for the Regional module."""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health_check(request: object) -> JsonResponse:
    """Expose process liveness only; readiness internals remain private."""

    del request
    return JsonResponse({"status": "ok", "module": "regional"})
