"""Black-box tenant isolation through real sessions and the governed v2 API."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.testing.tenant_contract import TenantIsolationContract

from ..models import (
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
    RiskConfiguration,
)
from .factories import (
    ComplianceCalendarEntryFactory,
    ComplianceRequirementFactory,
    ControlFactory,
    ControlTestFactory,
    RemediationActionFactory,
    RiskAssessmentFactory,
    RiskConfigurationFactory,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db

PREFIX = "/api/v2/compliance-risk-management"


@pytest.fixture(autouse=True)
def declared_access_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow declared permissions without bypassing auth, CSRF, or tenancy.

    Access-policy behavior has its own exhaustive suite.  Isolation needs an
    affirmative decision so every request reaches the production tenant
    resolver and tenant-filtered service/query path.
    """

    def allow(
        self: AccessDecisionPipeline,
        tenant_id: object,
        identity: object,
        required_permission: str,
        **kwargs: object,
    ) -> AccessDecision:
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="declared permission allowed for isolation proof",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", allow)


class GovernedV2IsolationContract(TenantIsolationContract):
    """Adapt the reusable contract to the governed success envelope."""

    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response: object) -> list[dict[str, object]]:
        payload = response.json()  # type: ignore[attr-defined]
        assert set(payload) >= {"data", "meta"}
        assert isinstance(payload["data"], list)
        return payload["data"]


@pytest.mark.django_db
class TestRiskAssessmentIsolation(GovernedV2IsolationContract):
    model = RiskAssessment
    list_url = f"{PREFIX}/risks/"
    detail_url_template = f"{PREFIX}/risks/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = RiskAssessmentFactory(tenant_id=tenant_a.id, created_by_id=actor, risk_code="TENANT-A")
        self.tenant_b_row = RiskAssessmentFactory(tenant_id=tenant_b.id, created_by_id=actor, risk_code="TENANT-B")
        self.create_payload = {
            "risk_code": f"SPOOF-{uuid.uuid4().hex[:8]}",
            "name": "Spoof attempt",
            "category": "compliance",
            "description": "Must bind to the authenticated tenant.",
            "likelihood": 2,
            "impact": 3,
            "owner_id": str(actor),
            "review_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "idempotency_key": f"risk-{uuid.uuid4()}",
        }


@pytest.mark.django_db
class TestControlIsolation(GovernedV2IsolationContract):
    model = Control
    list_url = f"{PREFIX}/controls/"
    detail_url_template = f"{PREFIX}/controls/{{pk}}/"
    update_payload = {"name": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        risk_a = RiskAssessmentFactory(tenant_id=tenant_a.id, created_by_id=actor)
        risk_b = RiskAssessmentFactory(tenant_id=tenant_b.id, created_by_id=actor)
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ControlFactory(
            tenant_id=tenant_a.id, created_by_id=actor, risk=risk_a, control_code="CTRL-A"
        )
        self.tenant_b_row = ControlFactory(
            tenant_id=tenant_b.id, created_by_id=actor, risk=risk_b, control_code="CTRL-B"
        )
        self.create_payload = {
            "risk_id": str(risk_a.id),
            "control_code": f"SPOOF-{uuid.uuid4().hex[:8]}",
            "name": "Spoof attempt",
            "description": "Tenant-bound control.",
            "test_procedure": "Inspect evidence.",
            "frequency": "monthly",
            "owner_id": str(actor),
            "next_test_due": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
        }


@pytest.mark.django_db
class TestControlTestIsolation(GovernedV2IsolationContract):
    model = ControlTest
    detail_url_template = f"{PREFIX}/tests/{{pk}}/"
    update_payload = {"scheduled_for": (dt.date.today() + dt.timedelta(days=60)).isoformat()}
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED})

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        control_a = ControlFactory(tenant_id=tenant_a.id, created_by_id=actor)
        control_b = ControlFactory(tenant_id=tenant_b.id, created_by_id=actor)
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ControlTestFactory(tenant_id=tenant_a.id, created_by_id=actor, control=control_a)
        self.tenant_b_row = ControlTestFactory(tenant_id=tenant_b.id, created_by_id=actor, control=control_b)
        self.list_url = f"{PREFIX}/controls/{control_a.id}/tests/"
        self.create_payload = {
            "scheduled_for": (dt.date.today() + dt.timedelta(days=45)).isoformat(),
            "tester_id": str(actor),
            "idempotency_key": f"test-{uuid.uuid4()}",
        }


@pytest.mark.django_db
class TestRequirementIsolation(GovernedV2IsolationContract):
    model = ComplianceRequirement
    list_url = f"{PREFIX}/requirements/"
    detail_url_template = f"{PREFIX}/requirements/{{pk}}/"
    update_payload = {"title": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceRequirementFactory(
            tenant_id=tenant_a.id, created_by_id=actor, requirement_code="REQ-A"
        )
        self.tenant_b_row = ComplianceRequirementFactory(
            tenant_id=tenant_b.id, created_by_id=actor, requirement_code="REQ-B"
        )
        self.create_payload = {
            "regulation_code": "REG",
            "requirement_code": f"SPOOF-{uuid.uuid4().hex[:8]}",
            "regulation_name": "Test Regulation",
            "title": "Spoof attempt",
            "description": "Must bind to the authenticated tenant.",
            "applicability": "mandatory",
            "owner_id": str(actor),
            "cross_references": [],
        }


@pytest.mark.django_db
class TestCalendarIsolation(GovernedV2IsolationContract):
    model = ComplianceCalendarEntry
    detail_url_template = f"{PREFIX}/calendar/{{pk}}/"
    update_payload = {"title": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        requirement_a = ComplianceRequirementFactory(tenant_id=tenant_a.id, created_by_id=actor)
        requirement_b = ComplianceRequirementFactory(tenant_id=tenant_b.id, created_by_id=actor)
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = ComplianceCalendarEntryFactory(
            tenant_id=tenant_a.id, created_by_id=actor, requirement=requirement_a
        )
        self.tenant_b_row = ComplianceCalendarEntryFactory(
            tenant_id=tenant_b.id, created_by_id=actor, requirement=requirement_b
        )
        start = dt.date.today().isoformat()
        end = (dt.date.today() + dt.timedelta(days=365)).isoformat()
        self.list_url = f"{PREFIX}/calendar/?date_from={start}&date_to={end}"
        self.create_payload = {
            "requirement_id": str(requirement_a.id),
            "title": f"Spoof-{uuid.uuid4().hex[:8]}",
            "event_type": "deadline",
            "scheduled_date": (dt.date.today() + dt.timedelta(days=60)).isoformat(),
            "reminder_days": [30, 14, 7, 1],
            "assigned_to_id": str(actor),
        }


@pytest.mark.django_db
class TestRemediationIsolation(GovernedV2IsolationContract):
    model = RemediationAction
    list_url = f"{PREFIX}/remediations/"
    detail_url_template = f"{PREFIX}/remediations/{{pk}}/"
    update_payload = {"description": "Cross-tenant mutation"}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        risk_a = RiskAssessmentFactory(tenant_id=tenant_a.id, created_by_id=actor)
        risk_b = RiskAssessmentFactory(tenant_id=tenant_b.id, created_by_id=actor)
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = RemediationActionFactory(
            tenant_id=tenant_a.id, created_by_id=actor, risk=risk_a, action_code="ACTION-A"
        )
        self.tenant_b_row = RemediationActionFactory(
            tenant_id=tenant_b.id, created_by_id=actor, risk=risk_b, action_code="ACTION-B"
        )
        self.create_payload = {
            "risk_id": str(risk_a.id),
            "action_code": f"SPOOF-{uuid.uuid4().hex[:8]}",
            "description": "Tenant-bound remediation.",
            "assigned_to_id": str(actor),
            "due_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "priority": "high",
        }


@pytest.mark.django_db
class TestRiskConfigurationIsolation(GovernedV2IsolationContract):
    """Configuration has publish semantics rather than conventional CRUD."""

    model = RiskConfiguration
    list_url = f"{PREFIX}/configuration/?environment=development"
    detail_url_template = f"{PREFIX}/configuration/versions/{{pk}}/"
    create_payload = {"unsupported": True}
    update_payload = {"unsupported": True}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        actor = uuid.uuid4()
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = RiskConfigurationFactory(tenant_id=tenant_a.id, created_by_id=actor, version=1)
        self.tenant_b_row = RiskConfigurationFactory(tenant_id=tenant_b.id, created_by_id=actor, version=7)

    def get_list_items(self, response: object) -> list[dict[str, object]]:
        payload = response.json()  # type: ignore[attr-defined]
        return [payload["data"]]

    def get_detail_url(self, row: RiskConfiguration) -> str:
        return f"{PREFIX}/configuration/versions/{row.version}/?environment=development"

    def test_spoofed_tenant_create_is_denied(self) -> None:
        before = RiskConfiguration.objects.filter(tenant_id=self.tenant_b_row.tenant_id).values().get()
        response = self.client.post(self.list_url, {"tenant_id": str(self.tenant_b_row.tenant_id)}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert RiskConfiguration.objects.filter(tenant_id=self.tenant_b_row.tenant_id).values().get() == before

    def test_cross_tenant_update_is_denied_and_unchanged(self) -> None:
        before = RiskConfiguration.objects.filter(pk=self.tenant_b_row.pk).values().get()
        response = self.client.patch(self.get_detail_url(self.tenant_b_row), {"version": 8}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert RiskConfiguration.objects.filter(pk=self.tenant_b_row.pk).values().get() == before

    def test_cross_tenant_delete_is_denied_and_unchanged(self) -> None:
        before = RiskConfiguration.objects.filter(pk=self.tenant_b_row.pk).values().get()
        response = self.client.delete(self.get_detail_url(self.tenant_b_row))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert RiskConfiguration.objects.filter(pk=self.tenant_b_row.pk).values().get() == before


@pytest.mark.parametrize(
    ("factory", "path", "payload"),
    [
        (RiskAssessmentFactory, "risks/{id}/transition/", {"command": "assess", "transition_key": "foreign"}),
        (ControlFactory, "controls/{id}/transition/", {"command": "activate", "transition_key": "foreign"}),
        (
            ComplianceRequirementFactory,
            "requirements/{id}/assess/",
            {"command": "assess_compliant", "rationale": "foreign", "evidence": [], "transition_key": "foreign"},
        ),
        (
            RemediationActionFactory,
            "remediations/{id}/transition/",
            {"command": "start", "transition_key": "foreign", "context": {}},
        ),
    ],
)
def test_cross_tenant_actions_are_404_and_unchanged(
    authenticated_tenant_a_client, tenant_b, factory, path: str, payload: dict[str, object]
) -> None:
    row = factory(tenant_id=tenant_b.id, created_by_id=uuid.uuid4())
    before = type(row).objects.filter(pk=row.pk).values().get()
    response = authenticated_tenant_a_client.post(f"{PREFIX}/{path.format(id=row.id)}", payload, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert type(row).objects.filter(pk=row.pk).values().get() == before
