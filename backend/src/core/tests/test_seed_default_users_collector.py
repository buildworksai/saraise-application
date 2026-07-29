"""Local access collector regression tests for development seeding."""

from __future__ import annotations

from src.core.management.commands.seed_default_users import Command


def test_local_access_collector_includes_crm_configuration_and_dynamic_api_quotas() -> None:
    permissions, resources, capabilities = Command()._collect_local_access_contracts()

    assert "crm" in capabilities
    assert "module.crm" in capabilities
    assert "crm.configuration:read" in permissions
    assert "crm.configuration:read" in capabilities | permissions
    assert "crm.api.list" in resources
    assert "crm.api.retrieve" in resources
    assert "backup-recovery" in capabilities
    assert "backup-recovery.job" in resources
    assert "backup-jobs-per-period" in resources
    assert "active-schedules" in resources
    assert "provider-probes" in resources
    assert "integrity-verifications" in resources
