"""Service-level proof for tenant safety, audit, scoring, and configuration."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from ..models import ComplianceActivity, ComplianceConfigurationRevision
from ..services import (
    AssessmentService, ComplianceConflict, ComplianceNotFound,
    ComplianceDashboardService, ComplianceDependencyUnavailable,
    ComplianceValidationError, ConfigurationService, EvidenceService,
    FrameworkService, MappingService, PolicyService, RequirementService,
)


pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def correlation():
    return uuid.uuid4()


def test_manual_loop_records_audit_and_calculates_deterministic_score():
    tenant = uuid.uuid4()
    framework = FrameworkService.create_framework(
        tenant, None,
        {"code": "ISO", "name": "ISO", "version": "1", "category": "General", "source_kind": "custom"},
        correlation(),
    )
    requirement = RequirementService.create_requirement(
        tenant, None,
        {"framework_id": framework.id, "code": "A.1", "title": "Governance", "description": "Define governance."},
        correlation(),
    )
    policy = PolicyService.create_policy(
        tenant, None,
        {"code": "POL-1", "title": "Governance policy", "category": "General"},
        correlation(),
    )
    mapping = MappingService.set_mapping(
        tenant, None, requirement.id, policy.id,
        {"coverage": "full", "rationale": "Complete policy coverage."},
        "map-1", correlation(),
    )
    AssessmentService.record_assessment(
        tenant, None,
        {"requirement_id": requirement.id, "mapping_id": mapping.id, "status": "partial", "notes": "Partially implemented.", "source": "manual"},
        "assessment-1", correlation(),
    )
    score = AssessmentService.scorecard(tenant, framework.id)
    assert score["score"] == 50.0
    assert "unassessed=0" in score["formula"]
    assert ComplianceActivity.objects.for_tenant(tenant).count() >= 5


def test_cross_tenant_related_identifier_is_invisible():
    first, second = uuid.uuid4(), uuid.uuid4()
    framework = FrameworkService.create_framework(
        first, None,
        {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom"},
        correlation(),
    )
    with pytest.raises(ComplianceNotFound):
        RequirementService.create_requirement(
            second, None,
            {"framework_id": framework.id, "code": "R", "title": "Requirement", "description": "Text"},
            correlation(),
        )


def test_configuration_preview_activation_export_import_and_rollback():
    tenant = uuid.uuid4()
    first = ConfigurationService.create_revision(tenant, None, "development", {}, correlation())
    preview = ConfigurationService.preview(tenant, first.id)
    assert preview["diff"]
    active = ConfigurationService.activate(tenant, None, first.id, "activate-1", correlation())
    assert active.status == "active"
    document = ConfigurationService.export_revision(tenant, active.id)
    imported = ConfigurationService.import_revision(tenant, None, document, correlation())
    rolled_back = ConfigurationService.rollback(tenant, None, active.id, "rollback-1", correlation())
    assert imported.status == "draft"
    assert rolled_back.version > active.version
    assert ConfigurationService.get_effective(tenant, "development").id == rolled_back.id


def test_client_lifecycle_status_and_unknown_fields_are_rejected():
    with pytest.raises(ComplianceValidationError):
        FrameworkService.create_framework(
            uuid.uuid4(), None,
            {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom", "status": "active"},
            correlation(),
        )


def test_framework_requirement_import_export_update_and_lifecycle():
    tenant = uuid.uuid4()
    package = {
        "schema": "saraise.compliance.framework/v1",
        "framework": {"code": "NIST", "name": "NIST CSF", "version": "2", "category": "General", "source_kind": "imported"},
        "requirements": [
            {"code": "GV.1", "title": "Govern", "description": "Govern security."},
            {"code": "ID.1", "title": "Identify", "description": "Identify assets.", "tags": ["asset"]},
        ],
    }
    assert FrameworkService.validate_import(tenant, package)["requirement_count"] == 2
    framework = FrameworkService.import_framework(tenant, None, package, "import-1", correlation())
    assert FrameworkService.import_framework(tenant, None, package, "import-1", correlation()).id == framework.id
    exported = FrameworkService.export_framework(tenant, framework.id)
    assert exported["schema"].endswith("/v1") and len(exported["requirements"]) == 2
    FrameworkService.update_framework(tenant, None, framework.id, {"description": "Updated"}, correlation())
    FrameworkService.activate_framework(tenant, None, framework.id, "activate", correlation())
    assert FrameworkService.activate_framework(tenant, None, framework.id, "activate", correlation()).status == "active"
    requirements = list(RequirementService.list_requirements(tenant, {"framework_id": framework.id, "search": "Govern"}))
    requirement = requirements[0]
    RequirementService.update_requirement(tenant, None, requirement.id, {"guidance": "Follow guidance."}, correlation())
    RequirementService.archive_requirement(tenant, None, requirement.id, "archive", correlation())
    restored = RequirementService.restore_requirement(tenant, None, requirement.id, "restore", correlation())
    assert restored.status == "active" and restored.deleted_at is None
    imported = RequirementService.bulk_import(
        tenant, None, framework.id,
        [{"code": "PR.1", "title": "Protect", "description": "Protect systems."}],
        "requirements-1", correlation(),
    )
    assert imported[0].framework_id == framework.id
    FrameworkService.archive_framework(tenant, None, framework.id, "archive-fw", correlation())
    with pytest.raises(ComplianceNotFound):
        FrameworkService.get_framework(tenant, framework.id)


def test_policy_full_publication_revision_and_archive(tenant_a, tenant_a_user):
    tenant = tenant_a.id
    policy = PolicyService.create_policy(
        tenant, tenant_a_user,
        {"code": "POL-PUB", "title": "Publishable", "category": "General", "owner_id": tenant_a_user.pk, "effective_date": timezone.now().date()},
        correlation(),
    )
    PolicyService.update_policy(tenant, tenant_a_user, policy.id, {"summary": "Reviewed policy."}, correlation())
    version = PolicyService.create_version(tenant, tenant_a_user, policy.id, "Policy content", "Initial", "version-1", correlation())
    assert version.version == 1
    assert PolicyService.create_version(tenant, tenant_a_user, policy.id, "Policy content", "Initial", "version-1", correlation()).id == version.id
    PolicyService.submit(tenant, tenant_a_user, policy.id, "submit", correlation())
    PolicyService.request_changes(tenant, tenant_a_user, policy.id, "Clarify scope", "changes", correlation())
    PolicyService.submit(tenant, tenant_a_user, policy.id, "submit-2", correlation())
    PolicyService.approve(tenant, tenant_a_user, policy.id, "approve", correlation())
    published = PolicyService.publish(tenant, tenant_a_user, policy.id, "publish", correlation())
    assert published.status == "published" and published.next_review_date is not None
    revised, second = PolicyService.revise(tenant, tenant_a_user, policy.id, "Revised content", "Annual revision", "revise", correlation())
    assert revised.status == "draft" and second.version == 2
    PolicyService.archive(tenant, tenant_a_user, policy.id, "archive", correlation())
    with pytest.raises(ComplianceNotFound):
        PolicyService.get_policy(tenant, policy.id)


def test_mapping_assessment_gap_history_and_overdue():
    tenant = uuid.uuid4()
    framework = FrameworkService.create_framework(tenant, None, {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom"}, correlation())
    requirements = RequirementService.bulk_import(
        tenant, None, framework.id,
        [{"code": "R1", "title": "One", "description": "One"}, {"code": "R2", "title": "Two", "description": "Two"}],
        "reqs", correlation(),
    )
    policy = PolicyService.create_policy(tenant, None, {"code": "P", "title": "Policy", "category": "General"}, correlation())
    mappings = MappingService.bulk_set_mappings(
        tenant, None,
        [{"requirement_id": requirements[0].id, "policy_id": policy.id, "coverage": "partial", "rationale": "Partial"}],
        "maps", correlation(),
    )
    gaps = MappingService.gap_analysis(tenant, framework.id)
    assert gaps["gap_count"] == 2
    assessment = AssessmentService.record_assessment(
        tenant, None,
        {"requirement_id": requirements[0].id, "mapping_id": mappings[0].id, "status": "non_compliant", "notes": "Control is not implemented.", "source": "manual", "due_date": timezone.now().date() - timedelta(days=1)},
        "assess", correlation(),
    )
    assert AssessmentService.get_assessment(tenant, assessment.id).id == assessment.id
    assert AssessmentService.current_for_requirement(tenant, requirements[0].id).id == assessment.id
    assert AssessmentService.history_for_requirement(tenant, requirements[0].id).count() == 1
    assert AssessmentService.list_overdue(tenant, timezone.now().date()).count() == 1
    MappingService.remove_mapping(tenant, None, mappings[0].id, correlation())
    assert MappingService.list_mappings(tenant).count() == 0


class _DmsValidator:
    def validate_document_reference(self, tenant_id, document_id):
        return {"tenant_id": tenant_id, "document_id": document_id, "valid": True}


def test_evidence_crud_links_freshness_and_dependency_failure():
    tenant = uuid.uuid4()
    framework = FrameworkService.create_framework(tenant, None, {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom"}, correlation())
    requirement = RequirementService.create_requirement(tenant, None, {"framework_id": framework.id, "code": "R", "title": "Requirement", "description": "Text"}, correlation())
    now = timezone.now()
    evidence = EvidenceService.register_evidence(
        tenant, None,
        {"name": "Attestation", "evidence_type": "attestation", "reference_kind": "text_reference", "text_reference": "Signed reference", "classification": "internal", "collection_method": "manual", "valid_from": now - timedelta(days=1), "valid_until": now + timedelta(days=5)},
        correlation(),
    )
    EvidenceService.update_evidence(tenant, None, evidence.id, {"description": "Reviewed"}, correlation())
    link = EvidenceService.link_requirement(tenant, None, evidence.id, requirement.id, {"relevance": "primary", "notes": "Primary proof"}, correlation())
    assert EvidenceService.list_evidence(tenant, {"requirement_id": requirement.id, "search": "Attest"}).count() == 1
    assert EvidenceService.validate_evidence(tenant, evidence.id, now)["fresh"] is True
    assert EvidenceService.list_expiring(tenant, now, 10).count() == 1
    EvidenceService.unlink_requirement(tenant, None, link.id, correlation())
    EvidenceService.archive_evidence(tenant, None, evidence.id, correlation())
    with pytest.raises(ComplianceNotFound):
        EvidenceService.get_evidence(tenant, evidence.id)
    EvidenceService.dms_validator = None
    with pytest.raises(ComplianceDependencyUnavailable):
        EvidenceService.register_evidence(
            tenant, None,
            {"name": "DMS", "evidence_type": "document", "reference_kind": "dms_document", "document_id": uuid.uuid4(), "classification": "restricted", "collection_method": "manual"},
            correlation(),
        )
    EvidenceService.dms_validator = _DmsValidator()
    dms = EvidenceService.register_evidence(
        tenant, None,
        {"name": "DMS", "evidence_type": "document", "reference_kind": "dms_document", "document_id": uuid.uuid4(), "classification": "restricted", "collection_method": "manual"},
        correlation(),
    )
    assert EvidenceService.validate_evidence(tenant, dms.id, now)["reference_valid"] is True
    EvidenceService.dms_validator = None


def test_configuration_draft_update_effective_failure_and_dashboard():
    tenant = uuid.uuid4()
    with pytest.raises(ComplianceDependencyUnavailable):
        ConfigurationService.get_effective(tenant, "development")
    revision = ConfigurationService.create_revision(tenant, None, "development", {}, correlation())
    updated = ConfigurationService.update_draft(tenant, None, revision.id, {"expiry_warning_days": 90}, correlation())
    assert updated.expiry_warning_days == 90
    ConfigurationService.activate(tenant, None, revision.id, "activate", correlation())
    with pytest.raises(ComplianceConflict):
        ConfigurationService.update_draft(tenant, None, revision.id, {"expiry_warning_days": 10}, correlation())
    framework = FrameworkService.create_framework(tenant, None, {"code": "FW", "name": "Framework", "version": "1", "category": "General", "source_kind": "custom"}, correlation())
    RequirementService.create_requirement(tenant, None, {"framework_id": framework.id, "code": "R", "title": "Requirement", "description": "Text"}, correlation())
    summary = ComplianceDashboardService.summary(tenant, framework.id)
    assert summary["frameworks"] == 1 and summary["unassessed_requirements"] == 1
    assert ComplianceDashboardService.readiness_breakdown(tenant, framework.id)["possible_points"] == 1
