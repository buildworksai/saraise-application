"""Governed v2 HTTP contract tests using real session authentication."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from src.core.access.decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode

from ..api import TenantGovernedViewSet
from ..models import RiskAssessment
from .factories import (
    ComplianceCalendarEntryFactory,
    ComplianceRequirementFactory,
    ControlFactory,
    ControlTestFactory,
    RemediationActionFactory,
    RiskAssessmentFactory,
)

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db

RISKS = "/api/v2/compliance-risk-management/risks/"


@pytest.fixture(autouse=True)
def declared_access_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            True,
            AccessReasonCode.ALLOW,
            "declared permission allowed for API contract proof",
            tenant_id=uuid.UUID(str(tenant_id)),
        )

    monkeypatch.setattr(AccessDecisionPipeline, "decide", allow)


def test_anonymous_collection_is_401(api_client) -> None:
    response = api_client.get(RISKS)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    body = response.json()
    assert body["error"]["code"]
    assert body["error"]["correlation_id"]


def test_list_uses_governed_envelope_pagination_and_tenant_scope(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    own = RiskAssessmentFactory(tenant_id=tenant_a.id, risk_code="OWN-RISK")
    foreign = RiskAssessmentFactory(tenant_id=tenant_b.id, risk_code="FOREIGN-RISK")
    response = authenticated_tenant_a_client.get(f"{RISKS}?page=1&page_size=25")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert set(body) >= {"data", "meta"}
    assert body["meta"]["pagination"]["page"] == 1
    identities = {item["id"] for item in body["data"]}
    assert str(own.id) in identities
    assert str(foreign.id) not in identities


def test_create_binds_authenticated_tenant_and_returns_201(authenticated_tenant_a_client, tenant_a, tenant_b) -> None:
    actor = uuid.uuid4()
    response = authenticated_tenant_a_client.post(
        RISKS,
        {
            "tenant_id": str(tenant_b.id),
            "risk_code": "API-001",
            "name": "API-created risk",
            "category": "compliance",
            "description": "Created through the governed API.",
            "likelihood": 2,
            "impact": 3,
            "owner_id": str(actor),
            "review_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "idempotency_key": "api-create-001",
        },
        format="json",
    )
    # The strict serializer rejects tenant_id rather than trusting it.
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not RiskAssessment.objects.filter(tenant_id=tenant_b.id, risk_code="API-001").exists()

    response = authenticated_tenant_a_client.post(
        RISKS,
        {
            "risk_code": "API-001",
            "name": "API-created risk",
            "category": "compliance",
            "description": "Created through the governed API.",
            "likelihood": 2,
            "impact": 3,
            "owner_id": str(actor),
            "review_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "idempotency_key": "api-create-001",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    created = RiskAssessment.objects.get(pk=body["data"]["id"])
    assert created.tenant_id == tenant_a.id
    assert body["data"]["inherent_score"] == "6.00"


@pytest.mark.parametrize(
    "query",
    ["unknown=value", "page_size=101", "ordering=description", "owner_id=not-a-uuid"],
)
def test_invalid_query_parameters_use_governed_400(authenticated_tenant_a_client, query: str) -> None:
    response = authenticated_tenant_a_client.get(f"{RISKS}?{query}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["correlation_id"]


def test_tenant_viewset_filter_helper_rejects_unsupported_protocol_values() -> None:
    factory = APIRequestFactory()
    view = TenantGovernedViewSet()
    request = Request(factory.get("/risks/?status=identified&page=2&page_size=50&ordering=-review_date"))
    view.request = request

    assert view._filters({"status"}) == {"status": "identified"}

    invalid_queries = (
        "unknown=value",
        "page=0",
        "page=not-int",
        "page_size=101",
    )
    for query in invalid_queries:
        invalid_view = TenantGovernedViewSet()
        invalid_view.request = Request(factory.get(f"/risks/?{query}"))
        with pytest.raises(ValidationError):
            invalid_view._filters({"status"})


def test_score_preview_is_non_persistent_and_explainable(authenticated_tenant_a_client, tenant_a) -> None:
    before = RiskAssessment.objects.for_tenant(tenant_a.id).count()
    response = authenticated_tenant_a_client.post(
        f"{RISKS}score-preview/", {"likelihood": 4, "impact": 5}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()["data"]
    assert body["inherent_score"] == "20.00"
    assert body["risk_level"] == "critical"
    assert body["explanation"]["formula"] == "likelihood × impact"
    assert RiskAssessment.objects.for_tenant(tenant_a.id).count() == before


def test_put_and_unsupported_media_type_are_rejected(authenticated_tenant_a_client, tenant_a) -> None:
    risk = RiskAssessmentFactory(tenant_id=tenant_a.id)
    assert (
        authenticated_tenant_a_client.put(f"{RISKS}{risk.id}/", {"name": "No PUT"}, format="json").status_code
        == status.HTTP_405_METHOD_NOT_ALLOWED
    )
    response = authenticated_tenant_a_client.post(
        RISKS, "risk_code=FORM", content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    }


def test_control_collection_create_nested_tests_and_transition(authenticated_tenant_a_client, tenant_a) -> None:
    actor = uuid.uuid4()
    risk = RiskAssessmentFactory(tenant_id=tenant_a.id, owner_id=actor)
    control_url = "/api/v2/compliance-risk-management/controls/"
    create_response = authenticated_tenant_a_client.post(
        control_url,
        {
            "risk_id": str(risk.id),
            "control_code": "ctrl-api",
            "name": "API access review",
            "description": "Verify privileged roles.",
            "test_procedure": "Inspect user access exports.",
            "frequency": "monthly",
            "owner_id": str(actor),
            "default_tester_id": str(actor),
            "next_test_due": (dt.date.today() + dt.timedelta(days=14)).isoformat(),
        },
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    control_id = create_response.json()["data"]["id"]

    list_response = authenticated_tenant_a_client.get(f"{control_url}?risk_id={risk.id}&ordering=next_test_due")
    assert list_response.status_code == status.HTTP_200_OK
    assert [item["id"] for item in list_response.json()["data"]] == [control_id]

    schedule_response = authenticated_tenant_a_client.post(
        f"{control_url}{control_id}/tests/",
        {
            "scheduled_for": (dt.date.today() + dt.timedelta(days=15)).isoformat(),
            "tester_id": str(actor),
            "idempotency_key": "api-control-test-schedule",
        },
        format="json",
    )
    assert schedule_response.status_code == status.HTTP_201_CREATED

    transition_response = authenticated_tenant_a_client.post(
        f"{control_url}{control_id}/transition/",
        {"command": "activate", "transition_key": "api-control-activate"},
        format="json",
    )
    assert transition_response.status_code == status.HTTP_200_OK
    assert transition_response.json()["data"]["status"] == "active"
    retired_response = authenticated_tenant_a_client.post(
        f"{control_url}{control_id}/transition/",
        {"command": "retire", "transition_key": "api-control-retire"},
        format="json",
    )
    assert retired_response.status_code == status.HTTP_200_OK
    assert retired_response.json()["data"]["status"] == "retired"


def test_requirement_calendar_remediation_routes_enforce_filters_and_commands(
    authenticated_tenant_a_client, tenant_a
) -> None:
    actor = uuid.uuid4()
    reference = ComplianceRequirementFactory(tenant_id=tenant_a.id, owner_id=actor, requirement_code="REF-1")
    requirement_url = "/api/v2/compliance-risk-management/requirements/"
    created = authenticated_tenant_a_client.post(
        requirement_url,
        {
            "regulation_code": "SOX",
            "requirement_code": "REQ-API",
            "regulation_name": "Sarbanes Oxley",
            "title": "Quarterly access certification",
            "description": "Access certifications must be retained.",
            "applicability": "mandatory",
            "owner_id": str(actor),
            "effective_date": dt.date.today().isoformat(),
            "due_date": (dt.date.today() + dt.timedelta(days=30)).isoformat(),
            "cross_references": [str(reference.id)],
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED
    requirement_id = created.json()["data"]["id"]

    assessed = authenticated_tenant_a_client.post(
        f"{requirement_url}{requirement_id}/assess/",
        {
            "command": "assess_partial",
            "rationale": "Evidence exists but one sample is pending.",
            "evidence": [],
            "transition_key": "api-requirement-assess",
        },
        format="json",
    )
    assert assessed.status_code == status.HTTP_200_OK
    assert assessed.json()["data"]["status"] == "partially_compliant"

    calendar_url = "/api/v2/compliance-risk-management/calendar/"
    scheduled_date = dt.date.today() + dt.timedelta(days=10)
    entry = authenticated_tenant_a_client.post(
        calendar_url,
        {
            "requirement_id": requirement_id,
            "title": "Submit access packet",
            "event_type": "submission",
            "scheduled_date": scheduled_date.isoformat(),
            "reminder_days": [7, 1],
            "assigned_to_id": str(actor),
        },
        format="json",
    )
    assert entry.status_code == status.HTTP_201_CREATED
    entry_id = entry.json()["data"]["id"]
    filtered = authenticated_tenant_a_client.get(
        f"{calendar_url}?date_from={dt.date.today().isoformat()}&date_to="
        f"{(dt.date.today() + dt.timedelta(days=20)).isoformat()}&event_type=submission&assigned_to_id={actor}"
    )
    assert filtered.status_code == status.HTTP_200_OK
    assert [item["id"] for item in filtered.json()["data"]] == [entry_id]
    completed = authenticated_tenant_a_client.post(
        f"{calendar_url}{entry_id}/transition/",
        {
            "command": "complete",
            "transition_key": "api-calendar-complete",
            "context": {"completion_notes": "Packet submitted."},
        },
        format="json",
    )
    assert completed.status_code == status.HTTP_200_OK
    assert completed.json()["data"]["status"] == "completed"

    risk = RiskAssessmentFactory(tenant_id=tenant_a.id, owner_id=actor)
    remediation_url = "/api/v2/compliance-risk-management/remediations/"
    remediation = authenticated_tenant_a_client.post(
        remediation_url,
        {
            "risk_id": str(risk.id),
            "action_code": "rem-api",
            "description": "Close residual access finding.",
            "assigned_to_id": str(actor),
            "due_date": (dt.date.today() + dt.timedelta(days=5)).isoformat(),
            "priority": "high",
        },
        format="json",
    )
    assert remediation.status_code == status.HTTP_201_CREATED
    remediation_id = remediation.json()["data"]["id"]
    started = authenticated_tenant_a_client.post(
        f"{remediation_url}{remediation_id}/transition/",
        {"command": "start", "transition_key": "api-remediation-start", "context": {}},
        format="json",
    )
    assert started.status_code == status.HTTP_200_OK
    assert started.json()["data"]["status"] == "in_progress"


def test_dashboard_heatmap_job_and_configuration_routes(authenticated_tenant_a_client, tenant_a, tenant_b) -> None:
    actor = uuid.uuid4()
    risk = RiskAssessmentFactory(
        tenant_id=tenant_a.id,
        owner_id=actor,
        likelihood=5,
        impact=5,
        inherent_score="25.00",
        risk_level="critical",
    )
    ControlFactory(tenant_id=tenant_a.id, risk=risk, owner_id=actor)
    ComplianceCalendarEntryFactory(
        tenant_id=tenant_a.id,
        assigned_to_id=actor,
        scheduled_date=dt.date.today() + dt.timedelta(days=3),
    )
    RemediationActionFactory(tenant_id=tenant_a.id, risk=risk, assigned_to_id=actor)
    RiskAssessmentFactory(tenant_id=tenant_b.id, risk_code="FOREIGN-DASHBOARD")

    dashboard = authenticated_tenant_a_client.get(f"/api/v2/compliance-risk-management/dashboard/?owner_id={actor}")
    assert dashboard.status_code == status.HTTP_200_OK
    assert dashboard.json()["data"]["total_risks"] == 1

    heatmap = authenticated_tenant_a_client.get("/api/v2/compliance-risk-management/heatmap/?status=identified")
    assert heatmap.status_code == status.HTTP_200_OK
    assert any(cell["count"] >= 1 and cell["level"] == "critical" for cell in heatmap.json()["data"])

    active_config = authenticated_tenant_a_client.get("/api/v2/compliance-risk-management/configuration/")
    assert active_config.status_code == status.HTTP_200_OK
    preview = authenticated_tenant_a_client.post(
        "/api/v2/compliance-risk-management/configuration/preview/",
        {
            "environment": "development",
            "candidate": {
                "likelihood_scale_max": 5,
                "impact_scale_max": 5,
                "level_thresholds": {
                    "negligible": 1,
                    "low": 4,
                    "medium": 9,
                    "high": 16,
                    "critical": 25,
                },
                "default_review_days": 365,
                "default_reminder_days": [30, 14, 7, 1],
                "acceptance_max_days": 365,
                "overdue_job_enabled": True,
                "feature_flags": {},
                "extension_config": {},
            },
        },
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert preview.json()["data"]["valid"] is True

    test = ControlTestFactory(tenant_id=tenant_a.id, control__risk=risk, tester_id=actor)
    from src.core.async_jobs.models import AsyncJob

    job = AsyncJob.objects.create(
        tenant_id=tenant_a.id,
        actor_id=actor,
        command="compliance_risk.recurring_control_tests",
        payload={"test_id": str(test.id)},
        idempotency_key="api-job-visible",
    )
    response = authenticated_tenant_a_client.get(f"/api/v2/compliance-risk-management/jobs/{job.id}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["command"] == "compliance_risk.recurring_control_tests"
