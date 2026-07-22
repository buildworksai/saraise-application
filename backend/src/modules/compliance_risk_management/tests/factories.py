"""Reusable, tenant-explicit factories for the compliance-risk domain."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from ..models import (
    ComplianceCalendarEntry,
    ComplianceRequirement,
    Control,
    ControlTest,
    RemediationAction,
    RiskAssessment,
    RiskConfiguration,
    RiskConfigurationVersion,
)


class TenantFactoryMixin(factory.django.DjangoModelFactory):
    class Meta:
        abstract = True

    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by_id = factory.LazyFunction(uuid.uuid4)


class RiskAssessmentFactory(TenantFactoryMixin):
    class Meta:
        model = RiskAssessment

    risk_code = factory.Sequence(lambda number: f"RISK-{number:05d}")
    name = factory.Sequence(lambda number: f"Risk {number}")
    category = "compliance"
    description = "A test risk with a concrete assessment."
    likelihood = 3
    impact = 3
    inherent_score = Decimal("9.00")
    risk_level = "medium"
    owner_id = factory.LazyFunction(uuid.uuid4)
    review_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=90))


class ControlFactory(TenantFactoryMixin):
    class Meta:
        model = Control

    risk = factory.SubFactory(RiskAssessmentFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    control_code = factory.Sequence(lambda number: f"CTRL-{number:05d}")
    name = factory.Sequence(lambda number: f"Control {number}")
    description = "A concrete preventative control."
    test_procedure = "Inspect the source record and retained evidence."
    frequency = "monthly"
    owner_id = factory.LazyFunction(uuid.uuid4)
    next_test_due = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))


class ControlTestFactory(TenantFactoryMixin):
    class Meta:
        model = ControlTest

    control = factory.SubFactory(ControlFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    scheduled_for = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))
    tester_id = factory.LazyFunction(uuid.uuid4)


class ComplianceRequirementFactory(TenantFactoryMixin):
    class Meta:
        model = ComplianceRequirement

    regulation_code = "REG"
    requirement_code = factory.Sequence(lambda number: f"REQ-{number:05d}")
    regulation_name = "Test Regulation"
    title = factory.Sequence(lambda number: f"Requirement {number}")
    description = "A concrete regulatory obligation."
    applicability = "mandatory"
    owner_id = factory.LazyFunction(uuid.uuid4)


class ComplianceCalendarEntryFactory(TenantFactoryMixin):
    class Meta:
        model = ComplianceCalendarEntry

    requirement = factory.SubFactory(
        ComplianceRequirementFactory,
        tenant_id=factory.SelfAttribute("..tenant_id"),
    )
    title = factory.Sequence(lambda number: f"Compliance deadline {number}")
    event_type = "deadline"
    scheduled_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))
    reminder_days = factory.LazyFunction(lambda: [30, 14, 7, 1])
    assigned_to_id = factory.LazyFunction(uuid.uuid4)


class RemediationActionFactory(TenantFactoryMixin):
    class Meta:
        model = RemediationAction

    risk = factory.SubFactory(RiskAssessmentFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    action_code = factory.Sequence(lambda number: f"ACTION-{number:05d}")
    description = "Resolve the verified control deficiency."
    assigned_to_id = factory.LazyFunction(uuid.uuid4)
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))
    priority = "high"


class RiskConfigurationFactory(TenantFactoryMixin):
    class Meta:
        model = RiskConfiguration

    environment = "development"
    version = 1
    published_at = factory.LazyFunction(timezone.now)
    published_by_id = factory.LazyFunction(uuid.uuid4)


class RiskConfigurationVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RiskConfigurationVersion

    tenant_id = factory.LazyFunction(uuid.uuid4)
    environment = "development"
    version = 1
    configuration = factory.LazyFunction(
        lambda: {
            "likelihood_scale_max": 5,
            "impact_scale_max": 5,
            "level_thresholds": {"negligible": 1, "low": 4, "medium": 9, "high": 16, "critical": 25},
            "default_review_days": 365,
            "default_reminder_days": [30, 14, 7, 1],
            "acceptance_max_days": 365,
            "overdue_job_enabled": True,
            "feature_flags": {},
        }
    )
    change_summary = "Initial configuration"
    actor_id = factory.LazyFunction(uuid.uuid4)
    correlation_id = factory.LazyFunction(lambda: str(uuid.uuid4()))


__all__ = [
    "ComplianceCalendarEntryFactory",
    "ComplianceRequirementFactory",
    "ControlFactory",
    "ControlTestFactory",
    "RemediationActionFactory",
    "RiskAssessmentFactory",
    "RiskConfigurationFactory",
    "RiskConfigurationVersionFactory",
]
