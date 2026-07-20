"""Contract tests for the additive governed API v2 primitives."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.exceptions import NotFound, Throttled, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from src.core.api import (
    API_V2_SETTINGS_PROFILE,
    CapabilityUnavailable,
    GovernedAPIViewMixin,
    GovernedMultipartAPIViewMixin,
    GovernedPageNumberPagination,
    OperationFailed,
    OperationResult,
    SuccessEnvelopeRenderer,
    operation_result_to_response,
    stable_exception_handler,
)
from src.core.api.envelope import bypasses_json_envelope, correlation_id_for_request, is_json_media_type


def _renderer_context(response: object, correlation_id: str = "req_contract_test_000001") -> dict[str, object]:
    return {
        "request": SimpleNamespace(correlation_id=correlation_id),
        "response": response,
    }


def test_success_envelope_shape_and_nested_data_payload() -> None:
    response = Response({"data": {"customer": "Acme"}})
    rendered = SuccessEnvelopeRenderer().render(
        response.data,
        accepted_media_type="application/json",
        renderer_context=_renderer_context(response),
    )

    payload = json.loads(rendered)
    assert payload["data"] == {"data": {"customer": "Acme"}}
    assert payload["meta"]["correlation_id"] == "req_contract_test_000001"
    assert payload["meta"]["timestamp"].endswith("Z")
    assert set(payload) == {"data", "meta"}


def test_success_envelope_rejects_double_render_and_204_is_empty() -> None:
    response = Response({"id": "record-1"})
    renderer = SuccessEnvelopeRenderer()
    context = _renderer_context(response)
    renderer.render(response.data, "application/json", context)

    with pytest.raises(RuntimeError, match="already enveloped"):
        renderer.render(response.data, "application/json", context)

    no_content = Response(status=status.HTTP_204_NO_CONTENT)
    assert renderer.render(None, "application/json", _renderer_context(no_content)) == b""


def test_operation_result_requires_evidence_and_maps_success() -> None:
    with pytest.raises(ValueError, match="require evidence"):
        OperationResult.succeeded({"id": "record-1"}, evidence={})

    result = OperationResult.succeeded(
        {"id": "record-1"},
        evidence={"record_id": "record-1", "affected_rows": 1},
        provider="database",
    )
    response = operation_result_to_response(result, success_status=status.HTTP_201_CREATED)

    assert result.unwrap() == {"id": "record-1"}
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data == {"id": "record-1"}
    with pytest.raises(ValueError, match="no exception"):
        result.to_exception()


def test_failed_and_unavailable_results_raise_typed_http_exceptions() -> None:
    failed = OperationResult.failed(
        code="WRITE_REJECTED",
        message="The write was rejected.",
        http_status=status.HTTP_409_CONFLICT,
    )
    with pytest.raises(OperationFailed) as failed_error:
        failed.to_response()
    assert failed_error.value.status_code == status.HTTP_409_CONFLICT

    unavailable = OperationResult.unavailable(
        capability="document-conversion",
        evidence={"attempted": True},
    )
    with pytest.raises(CapabilityUnavailable) as unavailable_error:
        unavailable.unwrap()
    assert unavailable_error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert unavailable_error.value.capability == "document-conversion"


def test_operation_results_reject_inconsistent_states() -> None:
    with pytest.raises(ValueError, match="provider"):
        OperationResult.succeeded("value", evidence={"id": "one"}, provider=" ")
    with pytest.raises(ValueError, match="cannot carry an error"):
        OperationResult(
            status="succeeded",
            value="value",
            evidence={"id": "one"},
            error_code="IMPOSSIBLE",
        )
    with pytest.raises(ValueError, match="cannot carry a value"):
        OperationResult(
            status="failed",
            value="not-allowed",
            error_code="FAILED",
            message="Failed.",
            http_status=400,
        )
    with pytest.raises(ValueError, match="4xx or 5xx"):
        OperationResult.failed(code="FAILED", message="Failed.", http_status=200)
    with pytest.raises(ValueError, match="capability"):
        OperationResult.unavailable(capability=" ")


def test_exception_handler_has_stable_validation_and_not_found_codes() -> None:
    request = SimpleNamespace(correlation_id="req_error_contract_0001")
    validation = stable_exception_handler(
        ValidationError({"email": ["This field is required."]}),
        {"request": request},
    )
    not_found = stable_exception_handler(NotFound(), {"request": request})

    assert validation.status_code == status.HTTP_400_BAD_REQUEST
    assert validation.data == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "detail": {"email": ["This field is required."]},
            "correlation_id": "req_error_contract_0001",
        }
    }
    assert not_found.status_code == status.HTTP_404_NOT_FOUND
    assert not_found.data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert set(not_found.data["error"]) == {"code", "message", "detail", "correlation_id"}


def test_exception_handler_maps_unavailable_to_503_without_exposing_evidence() -> None:
    exc = CapabilityUnavailable(
        capability="module-registry",
        detail={"capability": "module-registry"},
        evidence={"internal_url": "must-not-leak"},
    )
    response = stable_exception_handler(
        exc,
        {"request": SimpleNamespace(correlation_id="req_unavailable_000001")},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data == {
        "error": {
            "code": "CAPABILITY_UNAVAILABLE",
            "message": "The requested capability is currently unavailable.",
            "detail": {"capability": "module-registry"},
            "correlation_id": "req_unavailable_000001",
        }
    }
    assert "internal_url" not in json.dumps(response.data)


def test_exception_handler_safely_maps_unexpected_errors() -> None:
    response = stable_exception_handler(
        RuntimeError("database password must not leak"),
        {"request": SimpleNamespace()},
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["error"]["code"] == "INTERNAL_ERROR"
    assert "password" not in json.dumps(response.data)
    assert response.data["error"]["correlation_id"].startswith("req_")


def test_exception_handler_includes_retry_delay_for_throttling() -> None:
    response = stable_exception_handler(
        Throttled(wait=3),
        {"request": SimpleNamespace(correlation_id="req_throttled_000001")},
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["error"]["code"] == "RATE_LIMITED"
    assert response.data["error"]["detail"] == {"retry_after_seconds": 3}


def test_pagination_caps_page_size_and_renders_governed_metadata() -> None:
    request = Request(APIRequestFactory().get("/api/v2/items/?page_size=1000&page=2"))
    paginator = GovernedPageNumberPagination()
    page = paginator.paginate_queryset(list(range(205)), request)

    assert page == list(range(100, 200))
    response = paginator.get_paginated_response(page)
    rendered = SuccessEnvelopeRenderer().render(
        response.data,
        "application/json",
        _renderer_context(response, "req_pagination_000001"),
    )
    payload = json.loads(rendered)

    assert payload["data"] == list(range(100, 200))
    assert payload["meta"]["pagination"] == {
        "count": 205,
        "page": 2,
        "page_size": 100,
        "total_pages": 3,
        "has_next": True,
        "has_previous": True,
    }


def test_paginated_response_schema_matches_wire_contract() -> None:
    schema = GovernedPageNumberPagination().get_paginated_response_schema(
        {"type": "object", "properties": {"id": {"type": "string"}}}
    )

    assert schema["required"] == ["data", "meta"]
    assert schema["properties"]["data"]["type"] == "array"
    page_size = schema["properties"]["meta"]["properties"]["pagination"]["properties"]["page_size"]
    assert page_size == {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}

    with pytest.raises(RuntimeError, match="paginate_queryset"):
        GovernedPageNumberPagination().get_paginated_response([])


def test_binary_and_streaming_responses_bypass_json_envelope() -> None:
    pdf_bytes = b"%PDF-1.7 governed binary body"
    file_response = FileResponse(BytesIO(pdf_bytes), content_type="application/pdf")
    stream_response = StreamingHttpResponse(iter([pdf_bytes]), content_type="application/octet-stream")
    renderer = SuccessEnvelopeRenderer()

    assert bypasses_json_envelope(file_response, "application/pdf") is True
    assert bypasses_json_envelope(stream_response, "application/octet-stream") is True
    assert renderer.render(pdf_bytes, "application/pdf", _renderer_context(file_response)) == pdf_bytes
    assert renderer.render(pdf_bytes, "application/octet-stream", _renderer_context(stream_response)) == pdf_bytes


def test_non_json_structured_response_is_rejected_and_json_suffix_is_supported() -> None:
    response = Response({"not": "binary"})
    with pytest.raises(TypeError, match="Django byte or streaming response"):
        SuccessEnvelopeRenderer().render(
            response.data,
            "application/pdf",
            _renderer_context(response),
        )
    assert is_json_media_type("application/problem+json; charset=utf-8") is True
    assert is_json_media_type("application/pdf") is False
    assert is_json_media_type(None) is False


def test_envelope_negotiation_handles_raw_http_and_direct_render_calls() -> None:
    json_response = HttpResponse(content_type="application/health+json")
    binary_response = HttpResponse(content_type="image/png")

    assert bypasses_json_envelope(None, "application/json") is False
    assert bypasses_json_envelope(None, "image/png") is True
    assert bypasses_json_envelope(json_response, None) is False
    assert bypasses_json_envelope(binary_response, "application/json") is True
    assert SuccessEnvelopeRenderer().render(bytearray(b"raw"), "image/png", {}) == b"raw"
    assert SuccessEnvelopeRenderer().render("raw", "text/plain", {}) == b"raw"


def test_error_rendering_is_not_wrapped_as_success() -> None:
    response = Response(
        {"error": {"code": "VALIDATION_ERROR"}},
        status=status.HTTP_400_BAD_REQUEST,
    )
    rendered = SuccessEnvelopeRenderer().render(
        response.data,
        "application/json",
        _renderer_context(response),
    )
    assert json.loads(rendered) == {"error": {"code": "VALIDATION_ERROR"}}


def test_correlation_fallback_handles_immutable_request_objects() -> None:
    correlation_id = correlation_id_for_request(object())
    assert correlation_id.startswith("req_")
    assert len(correlation_id) == 28


def test_v2_profile_is_opt_in_and_does_not_flip_v1_global_renderer() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == ["rest_framework.renderers.JSONRenderer"]
    assert API_V2_SETTINGS_PROFILE["DEFAULT_RENDERER_CLASSES"] == ["src.core.api.envelope.SuccessEnvelopeRenderer"]
    assert GovernedAPIViewMixin.renderer_classes == (SuccessEnvelopeRenderer,)
    assert GovernedAPIViewMixin().get_exception_handler() is stable_exception_handler
    assert GovernedMultipartAPIViewMixin.parser_classes[-1].__name__ == "FormParser"


def test_v1_remains_raw_while_v2_mixin_is_mountable() -> None:
    class LegacyView(APIView):
        authentication_classes: list[type[object]] = []
        permission_classes: list[type[object]] = []

        def get(self, request: Request) -> Response:
            return Response({"legacy": True})

    class GovernedView(GovernedAPIViewMixin, APIView):
        authentication_classes: list[type[object]] = []
        permission_classes: list[type[object]] = []

        def get(self, request: Request) -> Response:
            return Response({"governed": True})

    factory = APIRequestFactory()
    legacy_response = LegacyView.as_view()(factory.get("/api/v1/legacy/"))
    governed_response = GovernedView.as_view()(factory.get("/api/v2/governed/"))
    legacy_response.render()
    governed_response.render()

    assert json.loads(legacy_response.content) == {"legacy": True}
    assert json.loads(governed_response.content)["data"] == {"governed": True}
