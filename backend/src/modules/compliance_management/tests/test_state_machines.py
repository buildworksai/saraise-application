from __future__ import annotations

import uuid
import hashlib
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from src.core.state_machine import GuardFailedError, IdempotencyConflictError, IllegalTransitionError, TerminalStateError
from src.modules.compliance_management.models import (
    ComplianceConfigurationRevision,
    ComplianceFramework,
    CompliancePolicy,
    CompliancePolicyVersion,
    ComplianceRequirement,
    ConfigurationEnvironment,
    FrameworkSourceKind,
    PolicyStatus,
)
from src.modules.compliance_management.state_machines import (
    CONFIGURATION_MACHINE,
    FRAMEWORK_MACHINE,
    POLICY_MACHINE,
    REQUIREMENT_MACHINE,
)


pytestmark = pytest.mark.django_db


def framework(tenant_id=None):
    return ComplianceFramework.objects.create(
        tenant_id=tenant_id or uuid.uuid4(),
        code=f"FW-{uuid.uuid4().hex[:8]}",
        name="Framework",
        version="1",
        category="security",
        source_kind=FrameworkSourceKind.CUSTOM,
    )


def requirement(parent):
    return ComplianceRequirement.objects.create(
        tenant_id=parent.tenant_id,
        framework=parent,
        code=f"REQ-{uuid.uuid4().hex[:8]}",
        title="Requirement",
        description="Normative text",
    )


def configuration(tenant_id=None):
    return ComplianceConfigurationRevision.objects.create(
        tenant_id=tenant_id or uuid.uuid4(),
        environment=ConfigurationEnvironment.DEVELOPMENT,
        version=1,
        policy_code_prefix="POL",
        default_review_frequency_days=365,
        expiry_warning_days=30,
        evidence_warning_days=30,
        minimum_assessment_note_length=10,
        allow_external_evidence_urls=False,
        bulk_import_row_limit=1000,
        regulation_categories=["security"],
        rollout={},
    )


def policy(status=PolicyStatus.DRAFT, tenant_id=None):
    return CompliancePolicy.objects.create(
        tenant_id=tenant_id or uuid.uuid4(),
        code=f"POL-{uuid.uuid4().hex[:8]}",
        title="Policy",
        category="security",
        review_frequency_days=365,
        status=status,
    )


def test_framework_every_legal_transition_and_terminal_state():
    item = framework()
    FRAMEWORK_MACHINE.apply(item, "activate", transition_key="activate")
    FRAMEWORK_MACHINE.apply(item, "archive", transition_key="archive")
    with pytest.raises(TerminalStateError):
        FRAMEWORK_MACHINE.apply(item, "activate", transition_key="again")
    assert [row["command"] for row in item.transition_history] == ["activate", "archive"]


def test_requirement_archive_restore_and_illegal_transition():
    item = requirement(framework())
    with pytest.raises(IllegalTransitionError):
        REQUIREMENT_MACHINE.apply(item, "restore", transition_key="illegal")
    REQUIREMENT_MACHINE.apply(item, "archive", transition_key="archive")
    REQUIREMENT_MACHINE.apply(item, "restore", transition_key="restore")
    assert item.status == "active"


def test_configuration_transitions_are_complete_and_terminal():
    revision = configuration()
    CONFIGURATION_MACHINE.apply(revision, "activate", transition_key="activate")
    CONFIGURATION_MACHINE.apply(revision, "supersede", transition_key="supersede")
    with pytest.raises(TerminalStateError):
        CONFIGURATION_MACHINE.apply(revision, "activate", transition_key="terminal")


def test_policy_submit_request_changes_approve_and_archive_paths():
    draft = policy()
    POLICY_MACHINE.apply(draft, "submit", transition_key="submit")
    POLICY_MACHINE.apply(draft, "request_changes", transition_key="changes")
    POLICY_MACHINE.apply(draft, "submit", transition_key="submit-2")
    POLICY_MACHINE.apply(draft, "approve", transition_key="approve")
    POLICY_MACHINE.apply(draft, "archive", transition_key="archive-approved")
    assert draft.status == PolicyStatus.ARCHIVED

    direct_draft = policy()
    POLICY_MACHINE.apply(direct_draft, "archive", transition_key="archive-draft")
    assert direct_draft.status == PolicyStatus.ARCHIVED


def test_policy_publish_guard_rolls_back_then_publish_revise_and_archive():
    tenant_id = uuid.uuid4()
    item = policy(PolicyStatus.APPROVED, tenant_id)
    with pytest.raises(GuardFailedError):
        POLICY_MACHINE.apply(item, "publish", transition_key="not-ready")
    item.refresh_from_db()
    assert item.status == PolicyStatus.APPROVED
    assert item.transition_history == []

    user = get_user_model().objects.create_user(username=f"owner-{uuid.uuid4()}")
    item.owner = user
    item.effective_date = date(2026, 1, 1)
    item.next_review_date = date(2027, 1, 1)
    item.current_version = 1
    item.save()
    CompliancePolicyVersion.objects.create(
        tenant_id=tenant_id,
        policy=item,
        version=1,
        content="Approved content",
        content_sha256=hashlib.sha256(b"Approved content").hexdigest(),
        change_summary="Initial",
        created_by=user,
    )
    POLICY_MACHINE.apply(item, "publish", transition_key="publish")
    POLICY_MACHINE.apply(item, "revise", transition_key="revise")
    POLICY_MACHINE.apply(item, "archive", transition_key="archive-revised")
    assert item.status == PolicyStatus.ARCHIVED


def test_same_key_is_idempotent_and_conflicting_command_rejected():
    item = framework()
    stale = ComplianceFramework.objects.get(pk=item.pk)
    FRAMEWORK_MACHINE.apply(item, "activate", transition_key="request-key")
    FRAMEWORK_MACHINE.apply(stale, "activate", transition_key="request-key")
    item.refresh_from_db()
    assert len(item.transition_history) == 1
    with pytest.raises(IdempotencyConflictError):
        FRAMEWORK_MACHINE.apply(item, "archive", transition_key="request-key")


def test_stale_callers_serialize_against_stored_state():
    item = requirement(framework())
    first = ComplianceRequirement.objects.get(pk=item.pk)
    stale = ComplianceRequirement.objects.get(pk=item.pk)
    REQUIREMENT_MACHINE.apply(first, "archive", transition_key="shared")
    REQUIREMENT_MACHINE.apply(stale, "archive", transition_key="shared")
    item.refresh_from_db()
    assert item.status == "archived"
    assert len(item.transition_history) == 1
