"""Mutation-hardening tests for the backup_disaster_recovery authorization contract."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from .. import permissions as permissions_module
from ..permissions import (
    ACCESS_RULES,
    BACKUP_EXECUTE,
    BACKUP_READ,
    CONFIG_READ,
    CONFIG_WRITE,
    ENTITLEMENT,
    EXERCISE_CREATE,
    EXERCISE_EXECUTE,
    EXERCISE_UPDATE,
    HEALTH_READ,
    PERMISSIONS,
    READ,
    REPORT_READ,
    RESTORE_CREATE,
    RESTORE_EXECUTE,
    RUNBOOK_CREATE,
    RUNBOOK_DELETE,
    RUNBOOK_PUBLISH,
    RUNBOOK_UPDATE,
    SOD_ACTIONS,
    VERIFY_POINT,
    AccessRule,
)


def _configuration_with_quota_costs(quota_costs: object) -> SimpleNamespace:
    return SimpleNamespace(document={"quota_costs": quota_costs})


class TestAccessRuleFields:
    def test_permission_and_quota_resource_are_stored_verbatim(self) -> None:
        rule = AccessRule("some.permission", "some.resource")
        assert rule.permission == "some.permission"
        assert rule.quota_resource == "some.resource"

    def test_quota_key_defaults_to_default(self) -> None:
        rule = AccessRule("some.permission", "some.resource")
        assert rule.quota_key == "default"

    def test_quota_key_can_be_overridden(self) -> None:
        rule = AccessRule("some.permission", "some.resource", "custom_key")
        assert rule.quota_key == "custom_key"

    def test_entitlement_defaults_to_module_entitlement(self) -> None:
        rule = AccessRule("some.permission", "some.resource")
        assert rule.entitlement == ENTITLEMENT
        assert rule.entitlement == "backup_disaster_recovery"

    def test_entitlement_can_be_overridden(self) -> None:
        rule = AccessRule("some.permission", "some.resource", entitlement="other")
        assert rule.entitlement == "other"

    def test_rule_is_frozen(self) -> None:
        rule = AccessRule("some.permission", "some.resource")
        with pytest.raises(AttributeError):
            rule.permission = "changed"  # type: ignore[misc]


class TestQuotaCostFor:
    def setup_method(self) -> None:
        self.tenant_id = uuid.uuid4()

    def _patched(self, configuration: SimpleNamespace):
        return patch.object(
            permissions_module,
            "get_configuration",
            create=True,
            return_value=configuration,
        )

    def test_resolves_configured_value_for_default_key(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": 3})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            assert rule.quota_cost_for(self.tenant_id) == 3

    def test_resolves_configured_value_for_custom_key(self) -> None:
        rule = AccessRule("perm", "resource", "backup_execution")
        configuration = _configuration_with_quota_costs({"backup_execution": 10})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            assert rule.quota_cost_for(self.tenant_id) == 10

    def test_passes_tenant_id_through_to_get_configuration(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": 1})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ) as mock_get:
            rule.quota_cost_for(self.tenant_id)
            mock_get.assert_called_once_with(self.tenant_id)

    def test_raises_when_quota_costs_is_missing(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = SimpleNamespace(document={})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota_costs configuration is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_quota_costs_is_not_a_dict(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs(["not", "a", "dict"])
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota_costs configuration is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_quota_costs_is_none(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs(None)
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota_costs configuration is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_key_is_missing_from_quota_costs(self) -> None:
        rule = AccessRule("perm", "resource", "missing_key")
        configuration = _configuration_with_quota_costs({"default": 1})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'missing_key' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_value_is_bool_true(self) -> None:
        # bool is a subclass of int in Python; the guard must explicitly reject it.
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": True})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'default' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_value_is_bool_false(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": False})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'default' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_value_is_not_an_int(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": "5"})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'default' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_value_is_zero(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": 0})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'default' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_raises_when_value_is_negative(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": -1})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            with pytest.raises(RuntimeError, match="quota cost 'default' is unavailable"):
                rule.quota_cost_for(self.tenant_id)

    def test_accepts_smallest_valid_value_of_one(self) -> None:
        rule = AccessRule("perm", "resource")
        configuration = _configuration_with_quota_costs({"default": 1})
        with patch(
            "src.modules.backup_disaster_recovery.services.get_configuration",
            return_value=configuration,
        ):
            assert rule.quota_cost_for(self.tenant_id) == 1


class TestRuleDefinitions:
    """Pin the exact policy/entitlement/quota metadata for each named rule."""

    @pytest.mark.parametrize(
        ("rule", "permission", "quota_resource", "quota_key"),
        [
            (READ, "backup_disaster_recovery.*:read", "bdr.api.read", "default"),
            (BACKUP_READ, "backup_disaster_recovery.backup:read", "bdr.api.read", "default"),
            (
                BACKUP_EXECUTE,
                "backup_disaster_recovery.backup:execute",
                "bdr.backup.execute",
                "backup_execution",
            ),
            (
                VERIFY_POINT,
                "backup_disaster_recovery.recovery_point:verify",
                "bdr.verification.execute",
                "verification",
            ),
            (
                RESTORE_CREATE,
                "backup_disaster_recovery.restore:create",
                "bdr.restore.validate",
                "restore_validation",
            ),
            (
                RESTORE_EXECUTE,
                "backup_disaster_recovery.restore:execute",
                "bdr.restore.execute",
                "restore_execution",
            ),
            (RUNBOOK_CREATE, "backup_disaster_recovery.runbook:create", "bdr.api.write", "default"),
            (RUNBOOK_UPDATE, "backup_disaster_recovery.runbook:update", "bdr.api.write", "default"),
            (RUNBOOK_DELETE, "backup_disaster_recovery.runbook:delete", "bdr.api.write", "default"),
            (RUNBOOK_PUBLISH, "backup_disaster_recovery.runbook:publish", "bdr.api.write", "default"),
            (EXERCISE_CREATE, "backup_disaster_recovery.exercise:create", "bdr.api.write", "default"),
            (EXERCISE_UPDATE, "backup_disaster_recovery.exercise:update", "bdr.api.write", "default"),
            (
                EXERCISE_EXECUTE,
                "backup_disaster_recovery.exercise:execute",
                "bdr.exercise.execute",
                "exercise_execution",
            ),
            (REPORT_READ, "backup_disaster_recovery.report:read", "bdr.api.read", "default"),
            (CONFIG_READ, "backup_disaster_recovery.configuration:read", "bdr.configuration.read", "default"),
            (CONFIG_WRITE, "backup_disaster_recovery.configuration:write", "bdr.configuration.write", "default"),
            (HEALTH_READ, "backup_disaster_recovery.health:read", "bdr.health.read", "default"),
        ],
    )
    def test_rule_metadata_is_pinned(self, rule: AccessRule, permission: str, quota_resource: str, quota_key: str) -> None:
        assert rule.permission == permission
        assert rule.quota_resource == quota_resource
        assert rule.quota_key == quota_key
        assert rule.entitlement == ENTITLEMENT


class TestPermissionsRegistry:
    def test_permissions_is_sorted(self) -> None:
        assert PERMISSIONS == sorted(PERMISSIONS)

    def test_permissions_contains_every_distinct_rule_permission(self) -> None:
        expected = {
            READ.permission,
            BACKUP_READ.permission,
            BACKUP_EXECUTE.permission,
            VERIFY_POINT.permission,
            RESTORE_CREATE.permission,
            RESTORE_EXECUTE.permission,
            RUNBOOK_CREATE.permission,
            RUNBOOK_UPDATE.permission,
            RUNBOOK_DELETE.permission,
            RUNBOOK_PUBLISH.permission,
            EXERCISE_CREATE.permission,
            EXERCISE_UPDATE.permission,
            EXERCISE_EXECUTE.permission,
            REPORT_READ.permission,
            CONFIG_READ.permission,
            CONFIG_WRITE.permission,
            HEALTH_READ.permission,
        }
        assert set(PERMISSIONS) == expected
        assert len(PERMISSIONS) == 17

    def test_permissions_has_no_duplicates(self) -> None:
        assert len(PERMISSIONS) == len(set(PERMISSIONS))

    def test_permissions_first_and_last_entries(self) -> None:
        assert PERMISSIONS[0] == sorted(PERMISSIONS)[0]
        assert PERMISSIONS[-1] == sorted(PERMISSIONS)[-1]


class TestSodActions:
    def test_sod_actions_exact_membership(self) -> None:
        assert SOD_ACTIONS == [
            "backup_disaster_recovery.restore:execute",
            "backup_disaster_recovery.runbook:publish",
        ]

    def test_sod_actions_length(self) -> None:
        assert len(SOD_ACTIONS) == 2

    def test_sod_actions_reference_restore_execute_and_runbook_publish_rules(self) -> None:
        assert RESTORE_EXECUTE.permission in SOD_ACTIONS
        assert RUNBOOK_PUBLISH.permission in SOD_ACTIONS
        assert READ.permission not in SOD_ACTIONS


class TestAccessRulesMapping:
    def test_access_rules_keys_match_expected_action_names(self) -> None:
        assert set(ACCESS_RULES.keys()) == {
            "read",
            "backup_read",
            "backup_execute",
            "recovery_point_verify",
            "restore_create",
            "restore_execute",
            "runbook_create",
            "runbook_update",
            "runbook_delete",
            "runbook_publish",
            "exercise_create",
            "exercise_update",
            "exercise_execute",
            "report_read",
            "configuration_read",
            "configuration_write",
            "health_read",
        }

    def test_access_rules_length(self) -> None:
        assert len(ACCESS_RULES) == 17

    @pytest.mark.parametrize(
        ("key", "rule"),
        [
            ("read", READ),
            ("backup_read", BACKUP_READ),
            ("backup_execute", BACKUP_EXECUTE),
            ("recovery_point_verify", VERIFY_POINT),
            ("restore_create", RESTORE_CREATE),
            ("restore_execute", RESTORE_EXECUTE),
            ("runbook_create", RUNBOOK_CREATE),
            ("runbook_update", RUNBOOK_UPDATE),
            ("runbook_delete", RUNBOOK_DELETE),
            ("runbook_publish", RUNBOOK_PUBLISH),
            ("exercise_create", EXERCISE_CREATE),
            ("exercise_update", EXERCISE_UPDATE),
            ("exercise_execute", EXERCISE_EXECUTE),
            ("report_read", REPORT_READ),
            ("configuration_read", CONFIG_READ),
            ("configuration_write", CONFIG_WRITE),
            ("health_read", HEALTH_READ),
        ],
    )
    def test_access_rules_maps_action_to_correct_rule_object(self, key: str, rule: AccessRule) -> None:
        assert ACCESS_RULES[key] is rule


class TestModuleExports:
    def test_all_exports_are_importable_and_exact(self) -> None:
        assert permissions_module.__all__ == [
            "ACCESS_RULES",
            "AccessRule",
            "CONFIG_READ",
            "CONFIG_WRITE",
            "ENTITLEMENT",
            "HEALTH_READ",
            "PERMISSIONS",
            "SOD_ACTIONS",
        ]

    def test_entitlement_constant_value(self) -> None:
        assert ENTITLEMENT == "backup_disaster_recovery"
