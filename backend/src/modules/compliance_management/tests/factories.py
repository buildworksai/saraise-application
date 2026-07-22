"""Valid-by-default factories for compliance contract and isolation tests."""

from __future__ import annotations

import hashlib
import uuid

import factory
from django.utils import timezone

from .. import models


class TenantFactory(factory.django.DjangoModelFactory):
    tenant_id = factory.LazyFunction(uuid.uuid4)

    class Meta:
        abstract = True


class ComplianceFrameworkFactory(TenantFactory):
    code = factory.Sequence(lambda n: f"FW-{n:04d}")
    name = factory.Sequence(lambda n: f"Framework {n}")
    version = "1.0"
    category = "General"
    source_kind = models.FrameworkSourceKind.CUSTOM

    class Meta:
        model = models.ComplianceFramework


class ComplianceRequirementFactory(TenantFactory):
    framework = factory.SubFactory(ComplianceFrameworkFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    code = factory.Sequence(lambda n: f"REQ-{n:04d}")
    title = factory.Sequence(lambda n: f"Requirement {n}")
    description = "A normative requirement."

    class Meta:
        model = models.ComplianceRequirement


class CompliancePolicyFactory(TenantFactory):
    code = factory.Sequence(lambda n: f"POL-{n:04d}")
    title = factory.Sequence(lambda n: f"Policy {n}")
    category = "General"
    review_frequency_days = 365

    class Meta:
        model = models.CompliancePolicy


class CompliancePolicyVersionFactory(TenantFactory):
    policy = factory.SubFactory(CompliancePolicyFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    version = 1
    content = factory.Sequence(lambda n: f"Policy content {n}")
    content_sha256 = factory.LazyAttribute(lambda value: hashlib.sha256(value.content.encode()).hexdigest())
    change_summary = "Initial version"

    class Meta:
        model = models.CompliancePolicyVersion


class RequirementPolicyMappingFactory(TenantFactory):
    requirement = factory.SubFactory(ComplianceRequirementFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    policy = factory.SubFactory(CompliancePolicyFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    coverage = models.MappingCoverage.FULL
    rationale = "Complete coverage."
    mapped_at = factory.LazyFunction(timezone.now)

    class Meta:
        model = models.RequirementPolicyMapping


class ComplianceAssessmentFactory(TenantFactory):
    requirement = factory.SubFactory(ComplianceRequirementFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    status = models.AssessmentStatus.COMPLIANT
    assessed_at = factory.LazyFunction(timezone.now)
    notes = "Verified manually."
    source = models.AssessmentSource.MANUAL

    class Meta:
        model = models.ComplianceAssessment


class ComplianceEvidenceFactory(TenantFactory):
    name = factory.Sequence(lambda n: f"Evidence {n}")
    evidence_type = models.EvidenceType.ATTESTATION
    reference_kind = models.EvidenceReferenceKind.TEXT_REFERENCE
    text_reference = "Verified operational record"
    classification = models.EvidenceClassification.INTERNAL
    collection_method = models.EvidenceCollectionMethod.MANUAL
    collected_at = factory.LazyFunction(timezone.now)

    class Meta:
        model = models.ComplianceEvidence


class ComplianceConfigurationRevisionFactory(TenantFactory):
    environment = models.ConfigurationEnvironment.DEVELOPMENT
    version = factory.Sequence(lambda n: n + 1)
    policy_code_prefix = "POL"
    default_review_frequency_days = 365
    expiry_warning_days = 30
    evidence_warning_days = 30
    minimum_assessment_note_length = 10
    allow_external_evidence_urls = False
    bulk_import_row_limit = 1000
    regulation_categories = ["General"]
    rollout = {"frameworks": {"enabled": True, "roles": [], "cohorts": []}}

    class Meta:
        model = models.ComplianceConfigurationRevision


class ComplianceActivityFactory(TenantFactory):
    entity_type = models.ActivityEntityType.POLICY
    entity_id = factory.LazyFunction(uuid.uuid4)
    action = "policy.created"
    correlation_id = factory.LazyFunction(uuid.uuid4)

    class Meta:
        model = models.ComplianceActivity
