"""Governed JSON response rendering for opt-in API v2 views.

Negotiation rule
----------------
Only successful DRF responses negotiated as ``application/json`` or a
``+json`` media type are enveloped.  Django ``FileResponse``,
``StreamingHttpResponse`` and byte ``HttpResponse`` objects never enter DRF's
renderer pipeline.  The defensive renderer check also passes through their
raw bytes if it is invoked directly.  A non-JSON response carrying structured
DRF data is rejected instead of being mislabeled or loaded into memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping
from uuid import uuid4

from django.http import FileResponse, HttpResponseBase, StreamingHttpResponse
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from src.core.middleware.correlation import get_correlation_id

_ENVELOPE_MARKER = "_saraise_v2_enveloped"
_PAGINATION_MARKER = "_saraise_v2_pagination"


def utc_timestamp() -> str:
    """Return an RFC 3339 UTC timestamp with millisecond precision."""

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def correlation_id_for_request(request: object | None) -> str:
    """Resolve the request correlation ID, creating one for direct unit calls."""

    correlation_id = getattr(request, "correlation_id", "") if request is not None else ""
    if not correlation_id:
        correlation_id = get_correlation_id()
    if not correlation_id:
        correlation_id = f"req_{uuid4().hex[:24]}"
        if request is not None:
            try:
                setattr(request, "correlation_id", correlation_id)
            except (AttributeError, TypeError):
                pass
    return correlation_id


def is_json_media_type(media_type: str | None) -> bool:
    """Return whether a negotiated media type represents JSON."""

    if not media_type:
        return False
    normalized = media_type.partition(";")[0].strip().lower()
    return normalized == "application/json" or normalized.endswith("+json")


def bypasses_json_envelope(response: HttpResponseBase | None, accepted_media_type: str | None) -> bool:
    """Return whether a response must bypass governed JSON wrapping."""

    if response is None:
        return not is_json_media_type(accepted_media_type)
    if response.status_code == 204:
        return True
    if isinstance(response, (FileResponse, StreamingHttpResponse)) or response.streaming:
        return True
    if isinstance(response, Response):
        return not is_json_media_type(accepted_media_type)

    content_type = response.get("Content-Type")
    return not is_json_media_type(content_type or accepted_media_type)


def _render_passthrough(data: object) -> bytes:
    """Return raw response bytes without consuming a stream."""

    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, (bytearray, memoryview)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8")
    raise TypeError("Non-JSON responses must use a Django byte or streaming response")


class SuccessEnvelopeRenderer(JSONRenderer):
    """Wrap successful API v2 JSON data exactly once."""

    media_type = "application/json"
    format = "json"

    def render(
        self,
        data: object,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, object] | None = None,
    ) -> bytes:
        context = renderer_context or {}
        response_object = context.get("response")
        response = response_object if isinstance(response_object, HttpResponseBase) else None

        if bypasses_json_envelope(response, accepted_media_type):
            return _render_passthrough(data)

        if response is not None and response.status_code >= 400:
            return super().render(data, accepted_media_type, dict(context))

        if response is not None and getattr(response, _ENVELOPE_MARKER, False):
            raise RuntimeError("API v2 response was already enveloped")

        request = context.get("request")
        meta: dict[str, object] = {
            "correlation_id": correlation_id_for_request(request),
            "timestamp": utc_timestamp(),
        }
        if response is not None:
            pagination = getattr(response, _PAGINATION_MARKER, None)
            if pagination is not None:
                meta["pagination"] = pagination
            setattr(response, _ENVELOPE_MARKER, True)

        envelope = {"data": data, "meta": meta}
        return super().render(envelope, accepted_media_type, dict(context))


# Explicit aliases keep the public contract readable for different consumers.
GovernedJSONRenderer = SuccessEnvelopeRenderer
SaraiseV2JSONRenderer = SuccessEnvelopeRenderer
