"""Integration-boundary contracts for compliance risk management."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.test import override_settings

from src.modules.compliance_risk_management import integrations


class _Breaker:
    state = SimpleNamespace(value="closed")


class _Response:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


class _Client:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, object]]] = []
        self.health_status = 200

    def request(self, method: str, path: str, **kwargs: object) -> _Response:
        self.requests.append((method, path, kwargs))
        return self.responses.pop(0)

    def get(self, path: str, **kwargs: object) -> _Response:
        self.requests.append(("GET", path, kwargs))
        return _Response(self.health_status, {"data": {"ready": self.health_status == 200}})

    def get_breaker(self, dependency: str) -> _Breaker:
        assert dependency in integrations.DEPENDENCIES
        return _Breaker()


def _config() -> dict[str, object]:
    return {
        "enabled": True,
        "base_url": "https://dms.internal",
        "allowed_hosts": ["dms.internal"],
        "connect_timeout": 1.0,
        "read_timeout": 2.0,
        "max_retries": 1,
        "retry_backoff": 0.01,
        "failure_threshold": 2,
        "reset_timeout": 30.0,
    }


def _evidence(tenant_id: uuid.UUID, *, checksum: str | None = None) -> tuple[dict[str, str], dict[str, object]]:
    checksum = checksum or ("a" * 64)
    reference = {
        "document_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
        "label": " SOC report ",
        "checksum": checksum.upper(),
    }
    acknowledgement = {
        "data": {
            "valid": True,
            "tenant_id": str(tenant_id),
            "checksum": checksum.lower(),
        }
    }
    return reference, acknowledgement


def test_validate_evidence_shape_normalizes_and_rejects_duplicate_versions() -> None:
    reference, _acknowledgement = _evidence(uuid.uuid4())

    normalized = integrations.validate_evidence_shape([reference])

    assert normalized == [
        {
            "document_id": reference["document_id"],
            "version_id": reference["version_id"],
            "label": "SOC report",
            "checksum": "a" * 64,
        }
    ]
    with pytest.raises(integrations.EvidenceValidationError, match="duplicate document version"):
        integrations.validate_evidence_shape([reference, {**reference, "label": "Copy"}])


@pytest.mark.parametrize(
    "evidence, message",
    [
        ("not-a-list", "must be an array"),
        ([{"document_id": str(uuid.uuid4())}], "must contain exactly"),
        (
            [
                {
                    "document_id": "not-a-uuid",
                    "version_id": str(uuid.uuid4()),
                    "label": "Evidence",
                    "checksum": "a" * 64,
                }
            ],
            "must be a valid UUID",
        ),
        (
            [
                {
                    "document_id": str(uuid.uuid4()),
                    "version_id": str(uuid.uuid4()),
                    "label": "Evidence",
                    "checksum": "z" * 64,
                }
            ],
            "SHA-256 or SHA-512",
        ),
    ],
)
def test_validate_evidence_shape_rejects_malformed_evidence(evidence: object, message: str) -> None:
    with pytest.raises((ValueError, integrations.EvidenceValidationError), match=message):
        integrations.validate_evidence_shape(evidence)


def test_unavailable_adapter_never_fabricates_success() -> None:
    adapter = integrations.UnavailableAdapter("dms")

    health = adapter.health()

    assert health.as_dict()["status"] == "unavailable"
    assert health.configured is False
    with pytest.raises(integrations.IntegrationUnavailable):
        adapter.verify_version(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "a" * 64)
    with pytest.raises(integrations.IntegrationUnavailable):
        adapter.start_workflow()
    with pytest.raises(AttributeError):
        getattr(adapter, "_private")


def test_build_registry_registers_enabled_adapters_and_skips_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[_Client] = []

    def client_factory(*args: object, **kwargs: object) -> _Client:
        del args, kwargs
        client = _Client([])
        clients.append(client)
        return client

    monkeypatch.setattr(integrations, "ResilientHttpClient", client_factory)

    registry = integrations.build_integration_registry(
        {
            "dms": _config(),
            "notifications": {"enabled": False},
        }
    )

    assert isinstance(registry.get("dms"), integrations.DMSAdapter)
    assert isinstance(registry.get("notifications"), integrations.UnavailableAdapter)
    assert len(clients) == 1


@pytest.mark.parametrize(
    "configuration, message",
    [
        ([], "must be an object"),
        ({"unknown": {"enabled": True}}, "Unknown compliance-risk integrations"),
        ({"dms": {"enabled": True, "allowed_hosts": ["dms.internal"]}}, "base_url must be configured"),
        ({"dms": {**_config(), "allowed_hosts": "dms.internal"}}, "allowed_hosts must be a non-empty array"),
        ({"dms": {**_config(), "max_retries": True}}, "max_retries must be an integer"),
        ({"dms": {**_config(), "connect_timeout": True}}, "connect_timeout must be a number"),
    ],
)
def test_build_registry_rejects_unsafe_configuration_shapes(configuration: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        integrations.build_integration_registry(configuration)


def test_dms_validate_evidence_requires_verified_same_tenant_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    reference, acknowledgement = _evidence(tenant_id)
    client = _Client([_Response(200, acknowledgement)])
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda *args, **kwargs: client)
    adapter = integrations.DMSAdapter("dms", _config())

    result = adapter.validate_evidence(tenant_id, [reference])

    assert result[0]["checksum"] == "a" * 64
    assert client.requests == [
        (
            "POST",
            "/api/v2/dms/evidence/verify/",
            {
                "dependency": "dms",
                "json": {
                    "tenant_id": str(tenant_id),
                    "document_id": reference["document_id"],
                    "version_id": reference["version_id"],
                    "label": "SOC report",
                    "checksum": "a" * 64,
                },
            },
        )
    ]


@pytest.mark.parametrize(
    "body, error",
    [
        ({"data": {"valid": True, "tenant_id": str(uuid.uuid4()), "checksum": "a" * 64}}, "another tenant"),
        ({"data": {"valid": True, "tenant_id": "TENANT", "checksum": "b" * 64}}, "checksum"),
        ({"data": {"valid": True, "tenant_id": None, "checksum": "a" * 64}}, "another tenant"),
        ({"data": {"valid": False, "tenant_id": "TENANT", "checksum": "a" * 64}}, "invalid"),
        ({"data": {"valid": True, "tenant_id": "TENANT", "checksum": "b" * 64}}, "checksum"),
    ],
)
def test_dms_validate_evidence_fails_closed_on_unverified_evidence(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
    error: str,
) -> None:
    tenant_id = uuid.uuid4()
    reference, _acknowledgement = _evidence(tenant_id)
    data = body["data"]
    if isinstance(data, dict) and data.get("tenant_id") == "TENANT":
        data["tenant_id"] = str(tenant_id)
    client = _Client([_Response(200, body)])
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda *args, **kwargs: client)
    adapter = integrations.DMSAdapter("dms", _config())

    with pytest.raises(integrations.EvidenceValidationError, match=error):
        adapter.validate_evidence(tenant_id, [reference])


@pytest.mark.parametrize(
    "response, error",
    [
        (_Response(503, {"data": {}}), integrations.EvidenceVerificationUnavailable),
        (_Response(200, ValueError("bad json")), integrations.EvidenceVerificationUnavailable),
        (_Response(200, []), integrations.EvidenceVerificationUnavailable),
        (_Response(200, {"data": []}), integrations.EvidenceVerificationUnavailable),
    ],
)
def test_dms_validate_evidence_treats_dependency_failures_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    response: _Response,
    error: type[Exception],
) -> None:
    tenant_id = uuid.uuid4()
    reference, _acknowledgement = _evidence(tenant_id)
    client = _Client([response])
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda *args, **kwargs: client)
    adapter = integrations.DMSAdapter("dms", _config())

    with pytest.raises(error):
        adapter.validate_evidence(tenant_id, [reference])


def test_notification_workflow_audit_and_reporting_acknowledgements_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(
        [
            _Response(202, {"data": {"id": "notification-1"}}),
            _Response(201, {"data": {"id": "workflow-1"}}),
            _Response(200, {"data": {"id": "audit-1"}}),
            _Response(202, {"data": {"id": "report-1"}}),
        ]
    )
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda *args, **kwargs: client)
    tenant_id = uuid.uuid4()

    notification = integrations.NotificationAdapter("notifications", _config()).enqueue_reminder(
        tenant_id,
        uuid.uuid4(),
        uuid.uuid4(),
        " reminder-key ",
    )
    workflow = integrations.WorkflowAdapter("workflow_automation", _config()).start_workflow(tenant_id, {"kind": "SOX"})
    audit = integrations.AuditAdapter("audit_trail", _config()).publish_audit_projection(tenant_id, {"event": "risk"})
    reporting = integrations.ReportingAdapter("reporting_analytics", _config()).publish_projection(
        tenant_id, {"metric": "open_risks"}
    )

    assert [result.external_id for result in (notification, workflow, audit, reporting)] == [
        "notification-1",
        "workflow-1",
        "audit-1",
        "report-1",
    ]
    assert all(result.accepted for result in (notification, workflow, audit, reporting))


def test_notification_acknowledgement_rejects_missing_external_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client([_Response(202, {"data": {"id": 42}})])
    monkeypatch.setattr(integrations, "ResilientHttpClient", lambda *args, **kwargs: client)

    with pytest.raises(integrations.InvalidIntegrationResponse, match="Notification acknowledgement"):
        integrations.NotificationAdapter("notifications", _config()).enqueue_reminder(
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            "key",
        )


def test_global_registry_helpers_validate_type_and_return_contract_adapters() -> None:
    registry = integrations.IntegrationRegistry()
    registry.register("dms", integrations.UnavailableAdapter("dms"))
    integrations.set_integration_registry(registry)

    assert integrations.get_integration_registry() is registry
    assert integrations.get_dms_adapter().name == "dms"
    with pytest.raises(TypeError):
        integrations.set_integration_registry(object())  # type: ignore[arg-type]


@override_settings(COMPLIANCE_RISK_INTEGRATIONS={})
def test_get_registry_refresh_rebuilds_from_settings() -> None:
    registry = integrations.get_integration_registry(refresh=True)

    assert isinstance(registry.get("dms"), integrations.UnavailableAdapter)
