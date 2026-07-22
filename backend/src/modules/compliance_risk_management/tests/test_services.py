"""Current tenant-first service behavior and failure-path tests."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from src.core.async_jobs.models import OutboxEvent

from ..models import Control, RiskAssessment
from ..services import ControlService, RiskAssessmentService, RiskConfigurationService
from .factories import RiskAssessmentFactory

pytestmark = pytest.mark.django_db


def _risk_payload(actor: uuid.UUID, code: str = "RISK-001") -> dict[str, object]:
    return {
        "risk_code": code,
        "name": "Payment compliance exposure",
        "category": "compliance",
        "description": "A material compliance exposure.",
        "likelihood": 3,
        "impact": 4,
        "owner_id": actor,
        "review_date": dt.date.today() + dt.timedelta(days=30),
    }


def test_score_preview_uses_configured_product_and_explanation() -> None:
    tenant = uuid.uuid4()
    result = RiskAssessmentService.preview_score(tenant, {"likelihood": 3, "impact": 4})
    assert result["inherent_score"] == Decimal("12.00")
    assert result["risk_level"] == "high"
    assert result["explanation"] == {
        "formula": "likelihood × impact",
        "likelihood": 3,
        "impact": 4,
        "threshold_version": 0,
        "matched_upper_bound": 16,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"likelihood": 0, "impact": 1},
        {"likelihood": 6, "impact": 1},
        {"likelihood": 2, "impact": 2, "residual_likelihood": 1},
    ],
)
def test_score_preview_rejects_boundaries_and_incomplete_residual(payload: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        RiskAssessmentService.preview_score(uuid.uuid4(), payload)


def test_create_risk_is_idempotent_tenant_scoped_and_emits_outbox() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    key = "create-risk-001"
    first = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), key)
    repeated = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), key)
    assert repeated.pk == first.pk
    assert first.risk_code == "RISK-001"
    assert first.inherent_score == Decimal("12.00")
    assert RiskAssessment.objects.for_tenant(tenant).count() == 1
    event = OutboxEvent.objects.for_tenant(tenant).get(event_type="risk.created.v1")
    assert event.aggregate_id == first.id
    assert event.payload["actor_id"] == str(actor)
    assert event.payload["correlation_id"]


def test_cross_tenant_get_update_delete_are_not_found_and_unchanged() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    foreign = RiskAssessmentFactory(tenant_id=tenant_b, created_by_id=actor, risk_code="FOREIGN")
    before = RiskAssessment.objects.filter(pk=foreign.pk).values().get()
    with pytest.raises(NotFound):
        RiskAssessmentService.get_risk(tenant_a, foreign.id)
    with pytest.raises(NotFound):
        RiskAssessmentService.update_risk(tenant_a, actor, foreign.id, {"name": "Tampered"})
    with pytest.raises(NotFound):
        RiskAssessmentService.soft_delete_risk(tenant_a, actor, foreign.id)
    assert RiskAssessment.objects.filter(pk=foreign.pk).values().get() == before


def test_transition_is_keyed_idempotent_and_illegal_new_key_is_rejected() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), "risk-transition-create")
    assessed = RiskAssessmentService.transition_risk(tenant, actor, risk.id, "assess", "assess-once")
    repeated = RiskAssessmentService.transition_risk(tenant, actor, risk.id, "assess", "assess-once")
    assert assessed.status == repeated.status == "assessed"
    assert len(repeated.transition_history) == 2
    with pytest.raises(ValidationError):
        RiskAssessmentService.transition_risk(tenant, actor, risk.id, "assess", "different-key")


def test_control_service_rejects_cross_tenant_parent() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    foreign_risk = RiskAssessmentFactory(tenant_id=tenant_b, created_by_id=actor)
    with pytest.raises(ValidationError):
        ControlService.create_control(
            tenant_a,
            actor,
            foreign_risk.id,
            {
                "control_code": "CTRL-001",
                "name": "Access review",
                "description": "Review access.",
                "test_procedure": "Inspect evidence.",
                "frequency": "monthly",
                "owner_id": actor,
            },
        )
    assert not Control.objects.for_tenant(tenant_a).exists()


def test_configuration_candidate_validation_is_fail_closed() -> None:
    valid = {
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
    }
    assert RiskConfigurationService.validate_candidate(dict(valid))["impact_scale_max"] == 5
    with pytest.raises(ValidationError):
        RiskConfigurationService.validate_candidate({**valid, "unknown": True})
    with pytest.raises(ValidationError):
        RiskConfigurationService.validate_candidate(
            {**valid, "level_thresholds": {**valid["level_thresholds"], "critical": 10}}
        )
