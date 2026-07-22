"""Transactional lifecycle definitions for compliance aggregates.

All commands use the shared state-machine engine, which locks the aggregate,
records an append-only transition value, and provides durable command-key
idempotency in one transaction.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.state_machine import StateMachine
from src.core.state_machine import register as register_state_machine
from src.core.state_machine import registry as state_machine_registry

from .models import (
    ComplianceConfigurationRevision,
    ComplianceFramework,
    CompliancePolicy,
    ComplianceRequirement,
    ConfigurationStatus,
    FrameworkStatus,
    PolicyStatus,
    RequirementStatus,
)


def _policy_is_publishable(policy: CompliancePolicy, context: Mapping[str, Any]) -> bool:
    """Enforce persistence-level publication guards under the row lock."""
    del context
    if (
        policy.current_version < 1
        or policy.owner_id is None
        or policy.effective_date is None
        or policy.next_review_date is None
    ):
        return False
    if policy.expiry_date is not None and policy.expiry_date <= policy.effective_date:
        return False
    return policy.versions.filter(version=policy.current_version).exists()


FRAMEWORK_MACHINE = StateMachine[ComplianceFramework](
    name="compliance_management.framework",
    model=ComplianceFramework,
    states=FrameworkStatus.values,
    transitions=(
        {"command": "activate", "from": FrameworkStatus.DRAFT, "to": FrameworkStatus.ACTIVE},
        {"command": "archive", "from": FrameworkStatus.ACTIVE, "to": FrameworkStatus.ARCHIVED},
    ),
    terminal_states=(FrameworkStatus.ARCHIVED,),
)


REQUIREMENT_MACHINE = StateMachine[ComplianceRequirement](
    name="compliance_management.requirement",
    model=ComplianceRequirement,
    states=RequirementStatus.values,
    transitions=(
        {"command": "archive", "from": RequirementStatus.ACTIVE, "to": RequirementStatus.ARCHIVED},
        {"command": "restore", "from": RequirementStatus.ARCHIVED, "to": RequirementStatus.ACTIVE},
    ),
)


POLICY_MACHINE = StateMachine[CompliancePolicy](
    name="compliance_management.policy",
    model=CompliancePolicy,
    states=PolicyStatus.values,
    transitions=(
        {"command": "submit", "from": PolicyStatus.DRAFT, "to": PolicyStatus.IN_REVIEW},
        {"command": "request_changes", "from": PolicyStatus.IN_REVIEW, "to": PolicyStatus.DRAFT},
        {"command": "approve", "from": PolicyStatus.IN_REVIEW, "to": PolicyStatus.APPROVED},
        {
            "command": "publish",
            "from": PolicyStatus.APPROVED,
            "to": PolicyStatus.PUBLISHED,
            "guards": (_policy_is_publishable,),
        },
        {"command": "archive", "from": PolicyStatus.DRAFT, "to": PolicyStatus.ARCHIVED},
        {"command": "archive", "from": PolicyStatus.APPROVED, "to": PolicyStatus.ARCHIVED},
        {"command": "archive", "from": PolicyStatus.PUBLISHED, "to": PolicyStatus.ARCHIVED},
        {"command": "revise", "from": PolicyStatus.PUBLISHED, "to": PolicyStatus.DRAFT},
    ),
    terminal_states=(PolicyStatus.ARCHIVED,),
)


CONFIGURATION_MACHINE = StateMachine[ComplianceConfigurationRevision](
    name="compliance_management.configuration",
    model=ComplianceConfigurationRevision,
    states=ConfigurationStatus.values,
    transitions=(
        {"command": "activate", "from": ConfigurationStatus.DRAFT, "to": ConfigurationStatus.ACTIVE},
        {"command": "supersede", "from": ConfigurationStatus.ACTIVE, "to": ConfigurationStatus.SUPERSEDED},
    ),
    terminal_states=(ConfigurationStatus.SUPERSEDED,),
)


def register_compliance_state_machines() -> None:
    """Register machines idempotently for autoreload and worker startup."""
    for name, machine in (
        ("compliance_management.framework", FRAMEWORK_MACHINE),
        ("compliance_management.requirement", REQUIREMENT_MACHINE),
        ("compliance_management.policy", POLICY_MACHINE),
        ("compliance_management.configuration", CONFIGURATION_MACHINE),
    ):
        if name not in state_machine_registry.names():
            register_state_machine(name, machine)


framework_machine = FRAMEWORK_MACHINE
requirement_machine = REQUIREMENT_MACHINE
policy_machine = POLICY_MACHINE
configuration_machine = CONFIGURATION_MACHINE


__all__ = [
    "CONFIGURATION_MACHINE",
    "FRAMEWORK_MACHINE",
    "POLICY_MACHINE",
    "REQUIREMENT_MACHINE",
    "configuration_machine",
    "framework_machine",
    "policy_machine",
    "register_compliance_state_machines",
    "requirement_machine",
]
