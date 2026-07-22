"""Persistence and lifecycle proof for compliance risk management."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.core.tenancy import TenantScopedModel, TimestampedModel
from src.modules.compliance_risk_management.models import (
    AppendOnlyViolation,
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
    RiskConfiguration,
    RiskConfigurationVersion,
)
from src.modules.compliance_risk_management.state_machines import (
    InvalidTransition,
    transition_calendar,
    transition_control,
    transition_control_test,
    transition_remediation,
    transition_requirement,
    transition_risk,
)

pytestmark = pytest.mark.django_db


def _risk(tenant_id: uuid.UUID, actor_id: uuid.UUID, **overrides: object) -> RiskAssessment:
    values: dict[str, object] = {
        "tenant_id": tenant_id,
        "created_by_id": actor_id,
        "risk_code": f"risk-{uuid.uuid4().hex[:8]}",
        "name": "Payment compliance exposure",
        "category": "compliance",
        "description": "A material compliance exposure.",
        "likelihood": 2,
        "impact": 2,
        "inherent_score": Decimal("4.00"),
        "risk_level": "medium",
        "owner_id": actor_id,
        "review_date": timezone.localdate() + dt.timedelta(days=30),
    }
    values.update(overrides)
    return RiskAssessment.objects.create(**values)


def _control(
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    risk: RiskAssessment,
    **overrides: object,
) -> Control:
    values: dict[str, object] = {
        "tenant_id": tenant_id,
        "created_by_id": actor_id,
        "risk": risk,
        "control_code": f"ctrl-{uuid.uuid4().hex[:8]}",
        "name": "Quarterly access review",
        "description": "Review privileged access.",
        "test_procedure": "Inspect approvals and revocations.",
        "frequency": "quarterly",
        "owner_id": actor_id,
    }
    values.update(overrides)
    return Control.objects.create(**values)


def _requirement(tenant_id: uuid.UUID, actor_id: uuid.UUID, **overrides: object) -> ComplianceRequirement:
    values: dict[str, object] = {
        "tenant_id": tenant_id,
        "created_by_id": actor_id,
        "regulation_code": f"reg-{uuid.uuid4().hex[:6]}",
        "requirement_code": f"req-{uuid.uuid4().hex[:6]}",
        "regulation_name": "Example Regulation",
        "title": "Access governance",
        "description": "Privileged access must be reviewed.",
        "applicability": "mandatory",
        "owner_id": actor_id,
    }
    values.update(overrides)
    return ComplianceRequirement.objects.create(**values)


@pytest.mark.parametrize(
    "model",
    [
        RiskAssessment,
        Control,
        ControlTest,
        ComplianceRequirement,
        ComplianceCalendarEntry,
        RemediationAction,
        RiskConfiguration,
    ],
)
def test_mutable_model_contract(model: type) -> None:
    assert issubclass(model, TenantScopedModel)
    assert issubclass(model, TimestampedModel)
    assert model._meta.get_field("tenant_id").db_index is True
    assert model._meta.get_field("tenant_id").get_internal_type() == "UUIDField"
    assert model._meta.get_field("created_by_id").db_index is True
    assert model._meta.get_field("is_deleted").default is False
    assert model._meta.get_field("transition_history").default is list


def test_risk_defaults_normalization_and_safe_string() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    risk = _risk(tenant, actor, risk_code="  fin-001  ")
    assert risk.risk_code == "FIN-001"
    assert risk.status == "identified"
    assert str(risk) == "FIN-001 - Payment compliance exposure"
    assert risk.description not in str(risk)


def test_risk_partial_unique_and_residual_override() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    first = _risk(tenant, actor, risk_code="R-1")
    with pytest.raises(IntegrityError), transaction.atomic():
        _risk(tenant, actor, risk_code="R-1")
    first.is_deleted = True
    first.deleted_at = timezone.now()
    first.deleted_by_id = actor
    first.save()
    assert _risk(tenant, actor, risk_code="R-1").pk != first.pk

    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        _risk(
            tenant,
            actor,
            residual_likelihood=3,
            residual_impact=3,
            residual_score=Decimal("9.00"),
        )
    overridden = _risk(
        tenant,
        actor,
        residual_likelihood=3,
        residual_impact=3,
        residual_score=Decimal("9.00"),
        qualitative_rationale="Approved temporary override.",
    )
    assert overridden.residual_score == Decimal("9.00")


def test_cross_tenant_control_and_custom_frequency_are_rejected() -> None:
    actor = uuid.uuid4()
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    risk = _risk(tenant_a, actor)
    with pytest.raises(ValidationError, match="same tenant"):
        _control(tenant_b, actor, risk)
    with pytest.raises(ValidationError):
        _control(tenant_a, actor, risk, frequency="custom", frequency_days=None)
    custom = _control(tenant_a, actor, risk, frequency="custom", frequency_days=90)
    assert custom.frequency_days == 90


def test_control_test_evidence_and_terminal_immutability() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    control = _control(tenant, actor, _risk(tenant, actor))
    evidence = [
        {
            "document_id": uuid.uuid4(),
            "version_id": uuid.uuid4(),
            "label": "Test evidence",
            "checksum": "sha256:example",
        }
    ]
    completed = ControlTest.objects.create(
        tenant_id=tenant,
        created_by_id=actor,
        control=control,
        scheduled_for=timezone.localdate(),
        started_at=timezone.now() - dt.timedelta(minutes=5),
        completed_at=timezone.now(),
        tester_id=actor,
        result="passed",
        evidence=evidence,
        status="completed",
    )
    assert isinstance(completed.evidence[0]["document_id"], str)
    completed.findings = "Tampered"
    with pytest.raises(AppendOnlyViolation):
        completed.save()
    with pytest.raises(AppendOnlyViolation):
        ControlTest.objects.filter(pk=completed.pk).update(findings="Tampered")
    with pytest.raises(AppendOnlyViolation):
        ControlTest.objects.filter(pk=completed.pk).delete()

    with pytest.raises(ValidationError):
        ControlTest.objects.create(
            tenant_id=tenant,
            created_by_id=actor,
            control=control,
            scheduled_for=timezone.localdate() + dt.timedelta(days=1),
            tester_id=actor,
            evidence=[{"document_id": "incomplete"}],
        )


def test_requirement_constraints_and_cross_references() -> None:
    tenant = uuid.uuid4()
    other_tenant = uuid.uuid4()
    actor = uuid.uuid4()
    referenced = _requirement(tenant, actor)
    other = _requirement(other_tenant, actor)
    requirement = _requirement(tenant, actor, cross_references=[referenced.id])
    assert requirement.cross_references == [str(referenced.id)]
    with pytest.raises(ValidationError):
        _requirement(tenant, actor, cross_references=[other.id])
    with pytest.raises(ValidationError):
        _requirement(
            tenant,
            actor,
            applicability="conditional",
            applicability_rationale="",
        )
    with pytest.raises(ValidationError):
        _requirement(
            tenant,
            actor,
            effective_date=dt.date(2030, 2, 1),
            due_date=dt.date(2030, 1, 1),
        )


def test_calendar_reminders_and_completion_contract() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    requirement = _requirement(tenant, actor)
    entry = ComplianceCalendarEntry.objects.create(
        tenant_id=tenant,
        created_by_id=actor,
        requirement=requirement,
        title="Annual filing",
        event_type="submission",
        scheduled_date=timezone.localdate() + dt.timedelta(days=30),
        reminder_days=[30, 14, 7, 1],
        assigned_to_id=actor,
    )
    assert entry.status == "upcoming"
    with pytest.raises(ValidationError):
        ComplianceCalendarEntry.objects.create(
            tenant_id=tenant,
            created_by_id=actor,
            requirement=requirement,
            title="Bad reminders",
            event_type="review",
            scheduled_date=timezone.localdate(),
            reminder_days=[7, 7, 14],
            assigned_to_id=actor,
        )


def test_remediation_requires_matching_test_and_completion_evidence() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    risk_a, risk_b = _risk(tenant, actor), _risk(tenant, actor)
    control = _control(tenant, actor, risk_a)
    test = ControlTest.objects.create(
        tenant_id=tenant,
        created_by_id=actor,
        control=control,
        scheduled_for=timezone.localdate(),
        tester_id=actor,
    )
    with pytest.raises(ValidationError, match="control test"):
        RemediationAction.objects.create(
            tenant_id=tenant,
            created_by_id=actor,
            risk=risk_b,
            control_test=test,
            action_code="A-1",
            description="Correct finding",
            assigned_to_id=actor,
            due_date=timezone.localdate() + dt.timedelta(days=10),
            priority="high",
        )
    with pytest.raises(ValidationError):
        RemediationAction.objects.create(
            tenant_id=tenant,
            created_by_id=actor,
            risk=risk_a,
            control_test=test,
            action_code="A-2",
            description="Correct finding",
            assigned_to_id=actor,
            due_date=timezone.localdate(),
            priority="high",
            status="completed",
            completion_date=timezone.localdate(),
            completion_evidence=[],
        )


def test_configuration_validation_and_immutable_history() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    config = RiskConfiguration.objects.create(
        tenant_id=tenant,
        created_by_id=actor,
        environment="production",
        version=1,
        published_at=timezone.now(),
        published_by_id=actor,
    )
    assert config.level_thresholds["critical"] == 25
    assert config.default_reminder_days == [30, 14, 7, 1]
    with pytest.raises(ValidationError):
        RiskConfiguration.objects.create(
            tenant_id=uuid.uuid4(),
            created_by_id=actor,
            environment="production",
            version=1,
            likelihood_scale_max=10,
            impact_scale_max=10,
            published_at=timezone.now(),
            published_by_id=actor,
        )

    snapshot = RiskConfigurationVersion.objects.create(
        tenant_id=tenant,
        environment="production",
        version=1,
        configuration={"version": 1},
        change_summary="Initial publication",
        actor_id=actor,
        correlation_id=uuid.uuid4(),
    )
    snapshot.change_summary = "Tampered"
    with pytest.raises(AppendOnlyViolation):
        snapshot.save()
    with pytest.raises(AppendOnlyViolation):
        RiskConfigurationVersion.objects.filter(pk=snapshot.pk).update(change_summary="Tampered")
    with pytest.raises(AppendOnlyViolation):
        RiskConfigurationVersion.objects.filter(pk=snapshot.pk).delete()


@pytest.mark.parametrize(
    ("resolver", "source", "command", "target"),
    [
        (transition_risk, "identified", "assess", "assessed"),
        (transition_risk, "mitigating", "accept", "accepted"),
        (transition_control, "draft", "activate", "active"),
        (transition_control_test, "in_progress", "record_result", "completed"),
        (transition_requirement, "non_compliant", "remediate", "compliant"),
        (transition_calendar, "upcoming", "mark_overdue", "overdue"),
        (transition_remediation, "overdue", "complete", "completed"),
    ],
)
def test_legal_state_transitions(resolver: object, source: str, command: str, target: str) -> None:
    assert resolver(source, command) == target  # type: ignore[operator]


@pytest.mark.parametrize(
    ("resolver", "source", "command"),
    [
        (transition_risk, "closed", "close"),
        (transition_control, "retired", "retire"),
        (transition_control_test, "completed", "start"),
        (transition_requirement, "compliant", "remediate"),
        (transition_calendar, "completed", "cancel"),
        (transition_remediation, "cancelled", "start"),
        (transition_risk, "identified", "unknown"),
    ],
)
def test_illegal_and_terminal_state_transitions(resolver: object, source: str, command: str) -> None:
    with pytest.raises(InvalidTransition):
        resolver(source, command)  # type: ignore[operator]


def test_database_unique_constraint_is_authoritative_under_concurrency_shape() -> None:
    tenant = uuid.uuid4()
    actor = uuid.uuid4()
    _risk(tenant, actor, risk_code="CONCURRENT-1")
    # ``bulk_create`` bypasses model validation, proving the database remains
    # the final line of defence under concurrent writers.
    duplicate = RiskAssessment(
        tenant_id=tenant,
        created_by_id=actor,
        risk_code="CONCURRENT-1",
        name="Duplicate",
        category="compliance",
        description="Duplicate",
        likelihood=1,
        impact=1,
        inherent_score=Decimal("1.00"),
        risk_level="negligible",
        owner_id=actor,
        review_date=timezone.localdate(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RiskAssessment.objects.bulk_create([duplicate])
