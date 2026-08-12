"""Current tenant-first service behavior and failure-path tests."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from src.core.api.results import OperationFailed
from src.core.async_jobs.models import OutboxEvent

from ..integrations import IntegrationResult
from ..models import ComplianceCalendarEntry, Control, RemediationAction, RiskAssessment
from ..services import (
    CapabilityUnavailable,
    ComplianceCalendarService,
    ComplianceRequirementService,
    ComplianceRiskService,
    ControlService,
    ControlTestService,
    RemediationService,
    RiskAssessmentService,
    RiskConfigurationService,
)
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


def _control_payload(actor: uuid.UUID, code: str = "CTRL-001") -> dict[str, object]:
    return {
        "control_code": code,
        "name": "Access review",
        "description": "Review access before quarter close.",
        "test_procedure": "Inspect access evidence.",
        "frequency": "monthly",
        "owner_id": actor,
        "default_tester_id": actor,
        "next_test_due": dt.date.today() + dt.timedelta(days=7),
    }


def _requirement_payload(actor: uuid.UUID, code: str = "REQ-001") -> dict[str, object]:
    return {
        "regulation_code": "SOX",
        "requirement_code": code,
        "regulation_name": "Sarbanes Oxley",
        "title": "Quarterly evidence review",
        "description": "Control evidence must be reviewed every quarter.",
        "applicability": "mandatory",
        "owner_id": actor,
        "effective_date": dt.date.today(),
        "due_date": dt.date.today() + dt.timedelta(days=30),
    }


def _evidence() -> list[dict[str, str]]:
    return [
        {
            "document_id": str(uuid.uuid4()),
            "version_id": str(uuid.uuid4()),
            "label": "Test packet",
            "checksum": "a" * 64,
        }
    ]


def _valid_config(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
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
    document.update(overrides)
    return document


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


def test_configuration_candidate_validation_normalizes_and_rejects_invalid_rollouts() -> None:
    candidate = RiskConfigurationService.validate_candidate(
        _valid_config(
            default_reminder_days=[7, 30, 7],
            feature_flags={"risk_heatmap": {"enabled": True, "roles": ["risk_admin"]}},
        )
    )
    assert candidate["default_reminder_days"] == [30, 7]

    invalid_candidates = (
        _valid_config(unknown_field=True),
        _valid_config(level_thresholds={"low": 4, "medium": 9, "high": 16, "critical": 25, "negligible": 1}),
        _valid_config(default_reminder_days=[1, "7"]),
        _valid_config(feature_flags={"unsupported": True}),
        _valid_config(feature_flags={"risk_heatmap": {"enabled": True, "roles": "risk_admin"}}),
        _valid_config(extension_config=[]),
    )
    for invalid in invalid_candidates:
        with pytest.raises(ValidationError):
            RiskConfigurationService.validate_candidate(invalid)


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


def test_risk_accept_close_reopen_guards_are_configured_and_audited() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), "risk-guard-create")
    assessed = RiskAssessmentService.transition_risk(tenant, actor, risk.id, "assess", "risk-guard-assess")

    with pytest.raises(ValidationError):
        RiskAssessmentService.transition_risk(tenant, actor, assessed.id, "accept", "risk-guard-accept-empty")
    with pytest.raises(ValidationError):
        RiskAssessmentService.transition_risk(
            tenant,
            actor,
            assessed.id,
            "accept",
            "risk-guard-accept-expired",
            {"accepted_until": dt.date.today().isoformat()},
        )

    accepted_until = dt.date.today() + dt.timedelta(days=30)
    accepted = RiskAssessmentService.transition_risk(
        tenant,
        actor,
        assessed.id,
        "accept",
        "risk-guard-accept",
        {"accepted_until": accepted_until.isoformat()},
    )
    assert accepted.status == "accepted"
    assert accepted.accepted_until == accepted_until

    RemediationService.create_action(
        tenant,
        actor,
        accepted.id,
        {
            "action_code": "REM-BLOCK-CLOSE",
            "description": "Close blocker.",
            "assigned_to_id": actor,
            "due_date": dt.date.today() + dt.timedelta(days=5),
            "priority": "medium",
        },
    )
    with pytest.raises(ValidationError):
        RiskAssessmentService.transition_risk(tenant, actor, accepted.id, "close", "risk-guard-close-blocked")

    cancelled = RemediationService.transition_action(
        tenant,
        actor,
        RemediationAction.objects.for_tenant(tenant).get(risk=accepted).id,
        "cancel",
        "risk-guard-cancel-remediation",
        {"cancellation_reason": "Risk acceptance superseded the planned remediation."},
    )
    assert cancelled.status == "cancelled"

    closed = RiskAssessmentService.transition_risk(tenant, actor, accepted.id, "close", "risk-guard-close")
    reopened = RiskAssessmentService.transition_risk(tenant, actor, closed.id, "reopen", "risk-guard-reopen")
    assert closed.closed_at is not None
    assert reopened.status == "assessed"
    assert reopened.accepted_until is None
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="risk.transitioned.v1").count() >= 3


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


def test_control_test_result_creates_remediation_and_follow_up(monkeypatch) -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()

    class DmsAdapter:
        def verify_version(self, tenant_id, document_id, version_id, checksum):
            assert tenant_id == tenant
            assert document_id and version_id and checksum == "a" * 64
            return True

    monkeypatch.setattr("src.modules.compliance_risk_management.integrations.get_dms_adapter", lambda: DmsAdapter())

    risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), "risk-for-control-test")
    control = ControlService.create_control(tenant, actor, risk.id, _control_payload(actor))
    scheduled = ControlTestService.schedule_test(
        tenant,
        actor,
        control.id,
        {"scheduled_for": control.next_test_due, "tester_id": actor},
        "schedule-key",
    )
    repeated = ControlTestService.schedule_test(
        tenant,
        actor,
        control.id,
        {"scheduled_for": control.next_test_due, "tester_id": actor},
        "schedule-key",
    )
    assert repeated.id == scheduled.id

    started = ControlTestService.start_test(tenant, actor, scheduled.id, "start-key")
    completed = ControlTestService.record_result(
        tenant,
        actor,
        started.id,
        {
            "result": "failed",
            "findings": "Role evidence is missing.",
            "evidence": _evidence(),
            "remediation": {
                "action_code": "REM-001",
                "description": "Collect missing role evidence.",
                "assigned_to_id": actor,
                "due_date": dt.date.today() + dt.timedelta(days=10),
                "priority": "high",
            },
        },
        "result-key",
    )

    assert completed.status == "completed"
    assert RemediationAction.objects.for_tenant(tenant).get(control_test=completed).action_code == "REM-001"
    ControlService.update_control(
        tenant,
        actor,
        control.id,
        {"next_test_due": control.next_test_due + dt.timedelta(days=31)},
    )
    follow_up = ControlTestService.create_follow_up_schedule(tenant, actor, completed.id)
    assert follow_up.control_id == control.id
    assert follow_up.id != completed.id


def test_calendar_due_reminders_fail_closed_and_mark_overdue(monkeypatch) -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()

    class RejectingNotificationAdapter:
        def enqueue_reminder(self, tenant_id, entry_id, assigned_to_id, idempotency_key):
            assert tenant_id == tenant
            assert entry_id and assigned_to_id == actor and idempotency_key
            return IntegrationResult(status="rejected", code="DOWNSTREAM_REJECTED")

    monkeypatch.setattr(
        "src.modules.compliance_risk_management.integrations.get_notification_adapter",
        lambda: RejectingNotificationAdapter(),
    )

    requirement = ComplianceRequirementService.create_requirement(tenant, actor, _requirement_payload(actor))
    entry = ComplianceCalendarService.create_entry(
        tenant,
        actor,
        {
            "requirement_id": requirement.id,
            "title": "Submit quarterly evidence",
            "event_type": "submission",
            "scheduled_date": dt.date.today() + dt.timedelta(days=7),
            "reminder_days": [1, 7, 7],
            "assigned_to_id": actor,
        },
    )

    assert entry.reminder_days == [7, 1]
    with pytest.raises(CapabilityUnavailable):
        ComplianceCalendarService.enqueue_due_reminders(tenant, actor, dt.date.today(), "reminder-batch")

    changed = ComplianceCalendarService.mark_overdue_batch(
        tenant,
        actor,
        dt.date.today() + dt.timedelta(days=8),
        uuid.uuid4(),
    )
    entry.refresh_from_db()
    assert changed == 1
    assert entry.status == "overdue"
    assert ComplianceCalendarEntry.objects.for_tenant(tenant).filter(status="overdue").count() == 1


def test_remediation_completion_requires_verified_evidence_and_terminal_update_is_rejected(monkeypatch) -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()

    class DmsAdapter:
        def verify_version(self, tenant_id, document_id, version_id, checksum):
            return tenant_id == tenant and bool(document_id and version_id and checksum)

    monkeypatch.setattr("src.modules.compliance_risk_management.integrations.get_dms_adapter", lambda: DmsAdapter())

    risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor), "risk-for-remediation")
    action = RemediationService.create_action(
        tenant,
        actor,
        risk.id,
        {
            "action_code": "rem-lowercase",
            "description": "Close evidence gap.",
            "assigned_to_id": actor,
            "due_date": dt.date.today() - dt.timedelta(days=1),
            "priority": "critical",
        },
    )
    assert action.action_code == "REM-LOWERCASE"

    with pytest.raises(ValidationError):
        RemediationService.transition_action(tenant, actor, action.id, "complete", "complete-empty", {})

    started = RemediationService.transition_action(tenant, actor, action.id, "start", "start-remediation")
    completed = RemediationService.transition_action(
        tenant,
        actor,
        started.id,
        "complete",
        "complete-remediation",
        {"completion_evidence": _evidence()},
    )
    assert completed.status == "completed"
    with pytest.raises(ValidationError):
        RemediationService.update_action(tenant, actor, completed.id, {"description": "tamper"})


def test_configuration_candidate_validation_is_fail_closed() -> None:
    valid = _valid_config()
    assert RiskConfigurationService.validate_candidate(dict(valid))["impact_scale_max"] == 5
    with pytest.raises(ValidationError):
        RiskConfigurationService.validate_candidate({**valid, "unknown": True})
    with pytest.raises(ValidationError):
        RiskConfigurationService.validate_candidate(
            {**valid, "level_thresholds": {**valid["level_thresholds"], "critical": 10}}
        )


@pytest.mark.parametrize(
    "candidate",
    [
        {"impact_scale_max": 5},
        _valid_config(likelihood_scale_max=2),
        _valid_config(default_reminder_days=[7, True]),
        _valid_config(default_review_days=0),
        _valid_config(acceptance_max_days=1096),
        _valid_config(level_thresholds={"critical": 25, "high": 16, "medium": 9, "low": 4, "negligible": 1}),
        _valid_config(level_thresholds={"negligible": 1, "low": 4, "medium": 4, "high": 16, "critical": 25}),
        _valid_config(feature_flags=[]),
        _valid_config(feature_flags={"unsupported": True}),
        _valid_config(feature_flags={"risk_heatmap": {"enabled": True, "roles": "admin"}}),
        _valid_config(extension_config=[]),
        _valid_config(extension_config={"missing-fragment": {}}),
    ],
)
def test_configuration_candidate_validation_rejects_unsafe_shapes(candidate: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RiskConfigurationService.validate_candidate(dict(candidate))


def test_configuration_environment_version_and_feature_rollout_fail_closed() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValidationError):
        RiskConfigurationService.get_active(tenant, "qa")
    with pytest.raises(NotFound):
        RiskConfigurationService.get_version(tenant, "development", 99)

    candidate = _valid_config(
        feature_flags={
            "risk_heatmap": {"enabled": True, "roles": [], "cohorts": ["beta"], "tenants": []},
            "dashboard": {"enabled": False},
        },
        change_summary="Scoped rollout",
    )
    RiskConfigurationService.publish(tenant, actor, "development", candidate, expected_version=0)

    assert RiskConfigurationService.evaluate_feature(tenant, "risk_heatmap", {"cohort": "beta"}) is True
    assert RiskConfigurationService.evaluate_feature(tenant, "dashboard", {"role": "risk_admin"}) is False


def test_configuration_publish_preview_import_rollback_and_feature_rollout() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    candidate = _valid_config(
        likelihood_scale_max=6,
        impact_scale_max=6,
        level_thresholds={"negligible": 1, "low": 6, "medium": 12, "high": 24, "critical": 36},
        default_reminder_days=[7, 30, 7, 1],
        feature_flags={"risk_heatmap": {"enabled": True, "roles": ["risk_admin"], "cohorts": [], "tenants": []}},
        change_summary="Raise risk matrix ceiling",
    )
    preview = RiskConfigurationService.preview(tenant, actor, "development", dict(candidate))
    assert preview["valid"] is True
    assert preview["score_band_changes"]

    published = RiskConfigurationService.publish(tenant, actor, "development", dict(candidate), expected_version=0)
    assert published.version == 1
    assert published.default_reminder_days == [30, 7, 1]
    assert RiskConfigurationService.evaluate_feature(tenant, "risk_heatmap", {"role": "risk_admin"}) is True
    assert RiskConfigurationService.evaluate_feature(tenant, "risk_heatmap", {"role": "viewer"}) is False
    assert RiskConfigurationService.evaluate_feature(tenant, "not_a_feature", {"role": "risk_admin"}) is False

    with pytest.raises(OperationFailed):
        RiskConfigurationService.publish(tenant, actor, "development", _valid_config(), expected_version=0)

    exported = RiskConfigurationService.export_document(tenant, "development")
    assert (
        RiskConfigurationService.import_document(tenant, actor, "development", exported, dry_run=True)["valid"] is True
    )
    with pytest.raises(ValidationError):
        RiskConfigurationService.import_document(tenant, actor, "production", exported, dry_run=True)

    updated = RiskConfigurationService.publish(
        tenant,
        actor,
        "development",
        _valid_config(
            level_thresholds={"negligible": 2, "low": 5, "medium": 10, "high": 20, "critical": 25},
            change_summary="Narrow medium band",
        ),
        expected_version=1,
    )
    rolled_back = RiskConfigurationService.rollback(tenant, actor, "development", published.version, updated.version)
    assert rolled_back.version == 3
    assert rolled_back.level_thresholds == published.level_thresholds
    assert RiskConfigurationService.get_version(tenant, "development", 1).version == 1
    assert OutboxEvent.objects.for_tenant(tenant).filter(event_type="configuration.rolled_back.v1").exists()


def test_risk_listing_dashboard_heatmap_and_legacy_adapter_are_tenant_scoped() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    overdue = RiskAssessmentService.create_risk(
        tenant,
        actor,
        _risk_payload(actor, "risk-past") | {"review_date": dt.date.today() - dt.timedelta(days=1)},
        "risk-past-key",
    )
    current = ComplianceRiskService.create_risk(
        tenant,
        risk_code="legacy-critical",
        risk_name="Legacy critical risk",
        risk_level="critical",
        owner_id=actor,
        review_date=dt.date.today() + dt.timedelta(days=90),
    )
    control = ControlService.create_control(
        tenant,
        actor,
        overdue.id,
        _control_payload(actor, "ctrl-past") | {"next_test_due": dt.date.today() - dt.timedelta(days=1)},
    )
    ControlService.transition_control(tenant, actor, control.id, "activate", "activate-overdue-control")
    requirement = ComplianceRequirementService.create_requirement(tenant, actor, _requirement_payload(actor))
    ComplianceCalendarService.create_entry(
        tenant,
        actor,
        {
            "requirement_id": requirement.id,
            "title": "Upcoming filing",
            "event_type": "submission",
            "scheduled_date": dt.date.today() + dt.timedelta(days=3),
            "reminder_days": [3],
            "assigned_to_id": actor,
        },
    )

    filtered = RiskAssessmentService.list_risks(
        tenant,
        {
            "category": "compliance",
            "risk_level": "critical",
            "status": "identified",
            "owner_id": actor,
            "search": "legacy",
            "review_from": dt.date.today(),
            "review_to": dt.date.today() + dt.timedelta(days=365),
        },
        ordering="-review_date",
    )
    summary = RiskAssessmentService.dashboard_summary(tenant)
    heatmap = RiskAssessmentService.heatmap(tenant, category="compliance", owner_id=actor, status="identified")

    assert list(filtered.values_list("id", flat=True)) == [current.id]
    assert summary["total_risks"] == 2
    assert summary["critical_risks"] == 1
    assert summary["overdue_reviews"] == 1
    assert summary["overdue_controls"] == 1
    assert summary["upcoming_events"] == 1
    assert {cell["count"] for cell in heatmap} == {1}
    with pytest.raises(ValidationError):
        RiskAssessmentService.list_risks(tenant, ordering="unsafe")


def test_requirement_calendar_and_remediation_guards_cover_terminal_and_reference_paths(monkeypatch) -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()

    class AcceptingDmsAdapter:
        def verify_version(self, tenant_id, document_id, version_id, checksum):
            return tenant_id == tenant and bool(document_id and version_id and checksum)

    class AcceptingNotificationAdapter:
        def enqueue_reminder(self, tenant_id, entry_id, assigned_to_id, idempotency_key):
            assert tenant_id == tenant
            assert entry_id and assigned_to_id == actor and idempotency_key
            return IntegrationResult(status="accepted", code="QUEUED")

    monkeypatch.setattr(
        "src.modules.compliance_risk_management.integrations.get_dms_adapter", lambda: AcceptingDmsAdapter()
    )
    monkeypatch.setattr(
        "src.modules.compliance_risk_management.integrations.get_notification_adapter",
        lambda: AcceptingNotificationAdapter(),
    )

    risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor, "risk-refs"), "risk-refs")
    other_risk = RiskAssessmentService.create_risk(tenant, actor, _risk_payload(actor, "risk-other"), "risk-other")
    requirement = ComplianceRequirementService.create_requirement(
        tenant, actor, _requirement_payload(actor, "req-main")
    )
    referenced = ComplianceRequirementService.create_requirement(
        tenant,
        actor,
        _requirement_payload(actor, "req-ref"),
    )
    assert ComplianceRequirementService.validate_cross_references(tenant, requirement.id, [referenced.id]) == [
        str(referenced.id)
    ]
    with pytest.raises(ValidationError):
        ComplianceRequirementService.validate_cross_references(tenant, requirement.id, [requirement.id])
    with pytest.raises(NotFound):
        ComplianceRequirementService.validate_cross_references(tenant, requirement.id, [uuid.uuid4()])

    assessed = ComplianceRequirementService.assess_requirement(
        tenant,
        actor,
        requirement.id,
        "assess_compliant",
        _evidence(),
        "Evidence packet supports compliance.",
        "requirement-assess",
    )
    assert assessed.status == "compliant"

    entry = ComplianceCalendarService.create_entry(
        tenant,
        actor,
        {
            "requirement_id": requirement.id,
            "title": "Evidence submission",
            "event_type": "submission",
            "scheduled_date": dt.date.today(),
            "reminder_days": [0, 0],
            "assigned_to_id": actor,
        },
    )
    assert ComplianceCalendarService.enqueue_due_reminders(tenant, actor, dt.date.today(), "calendar-reminder") == 1
    completed_entry = ComplianceCalendarService.transition_entry(
        tenant,
        actor,
        entry.id,
        "complete",
        "calendar-complete",
        {"completion_notes": "Submitted."},
    )
    assert completed_entry.completed_date == dt.date.today()
    with pytest.raises(ValidationError):
        ComplianceCalendarService.update_entry(tenant, actor, completed_entry.id, {"title": "Tamper"})
    with pytest.raises(ValidationError):
        ComplianceCalendarService.list_entries(tenant, None, dt.date.today())
    with pytest.raises(ValidationError):
        ComplianceCalendarService.list_entries(tenant, dt.date.today(), dt.date.today(), ordering="unsafe")
    ComplianceCalendarService.soft_delete_entry(tenant, actor, completed_entry.id)
    completed_entry.refresh_from_db()
    assert completed_entry.is_deleted is True

    control = ControlService.create_control(tenant, actor, risk.id, _control_payload(actor, "ctrl-rem"))
    test = ControlTestService.schedule_test(
        tenant,
        actor,
        control.id,
        {"scheduled_for": dt.date.today(), "tester_id": actor},
        "mismatch-test",
    )
    with pytest.raises(ValidationError):
        RemediationService.create_action(
            tenant,
            actor,
            other_risk.id,
            {
                "control_test_id": test.id,
                "action_code": "rem-mismatch",
                "description": "Wrong risk binding.",
                "assigned_to_id": actor,
                "due_date": dt.date.today(),
                "priority": "medium",
            },
        )
    action = RemediationService.create_action(
        tenant,
        actor,
        risk.id,
        {
            "action_code": "rem-overdue",
            "description": "Past due remediation.",
            "assigned_to_id": actor,
            "due_date": dt.date.today() - dt.timedelta(days=1),
            "priority": "medium",
        },
    )
    assert RemediationService.mark_overdue_batch(tenant, actor, dt.date.today(), uuid.uuid4()) == 1
    action.refresh_from_db()
    assert action.status == "overdue"
    with pytest.raises(ValidationError):
        RemediationService.transition_action(tenant, actor, action.id, "cancel", "cancel-without-reason")
    RemediationService.soft_delete_action(tenant, actor, action.id)
    action.refresh_from_db()
    assert action.is_deleted is True
