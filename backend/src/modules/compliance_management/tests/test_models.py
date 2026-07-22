"""Persistence invariants for the normalized compliance domain."""

import hashlib
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from ..models import ComplianceActivity, CompliancePolicyVersion
from .factories import (
    ComplianceActivityFactory, ComplianceConfigurationRevisionFactory,
    ComplianceFrameworkFactory, CompliancePolicyFactory,
    CompliancePolicyVersionFactory, ComplianceRequirementFactory,
    RequirementPolicyMappingFactory,
)


pytestmark = pytest.mark.django_db


def test_models_use_indexed_uuid_tenant_field():
    for factory_class in (
        ComplianceFrameworkFactory, ComplianceRequirementFactory,
        CompliancePolicyFactory, RequirementPolicyMappingFactory,
        ComplianceConfigurationRevisionFactory,
    ):
        field = factory_class._meta.model._meta.get_field("tenant_id")
        assert field.get_internal_type() == "UUIDField"
        assert field.db_index is True


def test_framework_unique_code_version_per_live_tenant():
    framework = ComplianceFrameworkFactory()
    with pytest.raises((ValidationError, IntegrityError)):
        ComplianceFrameworkFactory(
            tenant_id=framework.tenant_id,
            code=framework.code,
            version=framework.version,
        )


def test_cross_tenant_mapping_is_rejected():
    requirement = ComplianceRequirementFactory()
    policy = CompliancePolicyFactory()
    with pytest.raises(ValidationError):
        RequirementPolicyMappingFactory(
            tenant_id=requirement.tenant_id,
            requirement=requirement,
            policy=policy,
        )


def test_policy_version_hash_and_append_only_contract():
    version = CompliancePolicyVersionFactory()
    assert version.content_sha256 == hashlib.sha256(version.content.encode()).hexdigest()
    version.change_summary = "tampered"
    with pytest.raises(ValidationError):
        version.save()
    with pytest.raises(ValidationError):
        version.delete()


def test_activity_is_append_only_and_string_has_context():
    activity = ComplianceActivityFactory()
    assert activity.action in str(activity)
    activity.reason = "tampered"
    with pytest.raises(ValidationError):
        activity.save()
    with pytest.raises(ValidationError):
        ComplianceActivity.objects.filter(pk=activity.pk).delete()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_review_frequency_days", 0),
        ("expiry_warning_days", 366),
        ("evidence_warning_days", 366),
        ("minimum_assessment_note_length", 2001),
        ("bulk_import_row_limit", 10001),
    ],
)
def test_configuration_safe_bounds_are_unsavable(field, value):
    revision = ComplianceConfigurationRevisionFactory.build(**{field: value})
    with pytest.raises(ValidationError):
        revision.full_clean()
