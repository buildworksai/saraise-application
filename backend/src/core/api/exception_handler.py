"""Stable, non-leaking error responses for governed API v2 views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .envelope import correlation_id_for_request
from .results import OperationFailed


@dataclass(frozen=True, slots=True)
class ErrorDescriptor:
    """Stable public classification for a DRF exception."""

    code: str
    message: str


_ERROR_MAPPINGS: tuple[tuple[type[Exception], ErrorDescriptor], ...] = (
    (ValidationError, ErrorDescriptor("VALIDATION_ERROR", "Request validation failed.")),
    (NotAuthenticated, ErrorDescriptor("AUTHENTICATION_REQUIRED", "Authentication is required.")),
    (AuthenticationFailed, ErrorDescriptor("AUTHENTICATION_REQUIRED", "Authentication is required.")),
    (PermissionDenied, ErrorDescriptor("POLICY_DENIED", "You do not have permission to perform this action.")),
    (NotFound, ErrorDescriptor("RESOURCE_NOT_FOUND", "The requested resource was not found.")),
    (MethodNotAllowed, ErrorDescriptor("METHOD_NOT_ALLOWED", "This method is not allowed for the resource.")),
    (NotAcceptable, ErrorDescriptor("NOT_ACCEPTABLE", "The requested response format is not available.")),
    (
        UnsupportedMediaType,
        ErrorDescriptor("UNSUPPORTED_MEDIA_TYPE", "The request media type is not supported."),
    ),
    (Throttled, ErrorDescriptor("RATE_LIMITED", "The request rate limit was exceeded.")),
)


def _descriptor_for_exception(exc: Exception) -> ErrorDescriptor:
    if isinstance(exc, OperationFailed):
        return ErrorDescriptor(exc.error_code, exc.public_message)
    for exception_type, descriptor in _ERROR_MAPPINGS:
        if isinstance(exc, exception_type):
            return descriptor
    return ErrorDescriptor("INTERNAL_ERROR", "An unexpected error occurred.")


def _detail_for_exception(exc: Exception, response: Response | None) -> object:
    if isinstance(exc, OperationFailed):
        return exc.error_detail if exc.error_detail is not None else {}
    if response is not None and isinstance(exc, ValidationError):
        return response.data
    if isinstance(exc, Throttled):
        return {"retry_after_seconds": getattr(exc, "wait", None)}
    return {}


def stable_exception_handler(exc: Exception, context: Mapping[str, object]) -> Response:
    """Return the v2 error contract for handled and unexpected exceptions."""

    response = drf_exception_handler(exc, dict(context))
    if response is None:
        response = Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    descriptor = _descriptor_for_exception(exc)
    request = context.get("request")
    response.data = {
        "error": {
            "code": descriptor.code,
            "message": descriptor.message,
            "detail": _detail_for_exception(exc, response),
            "correlation_id": correlation_id_for_request(request),
        }
    }
    setattr(response, "_saraise_v2_error_enveloped", True)
    return response


# DRF settings convention and a concise import both resolve to the same handler.
saraise_exception_handler = stable_exception_handler
exception_handler = stable_exception_handler
