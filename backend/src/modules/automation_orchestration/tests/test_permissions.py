"""Security metadata, access requirements, and authentication contracts."""

import dataclasses
import pytest
from rest_framework.authentication import SessionAuthentication

from .. import permissions as permissions_module
from ..api import GovernedTenantViewSet
from ..permissions import (
    AccessRequirement,
    CATALOG_VIEW,
    CONFIGURATION_MANAGE,
    CONFIGURATION_VIEW,
    DEFINITION_MANAGE,
    DEFINITION_PUBLISH,
    DEFINITION_VIEW,
    HEALTH_VIEW,
    PERMISSIONS,
    RUN_CONTROL,
    RUN_EXECUTE,
    RUN_RETRY,
    RUN_VIEW,
    SCHEDULE_MANAGE,
    SCHEDULE_VIEW,
    SOD_ACTIONS,
    read_access,
    write_access,
)


def test_permission_catalog_is_exact_and_contains_no_generic_resource_permissions() -> None:
    assert len(PERMISSIONS) == 10
    assert len(set(PERMISSIONS)) == len(PERMISSIONS)
    assert all(permission.startswith("automation_orchestration.") for permission in PERMISSIONS)
    assert all("resource:" not in permission for permission in PERMISSIONS)
    assert PERMISSIONS == (
        DEFINITION_VIEW,
        DEFINITION_MANAGE,
        DEFINITION_PUBLISH,
        SCHEDULE_VIEW,
        SCHEDULE_MANAGE,
        RUN_VIEW,
        RUN_EXECUTE,
        RUN_CONTROL,
        RUN_RETRY,
        CATALOG_VIEW,
    )


def test_derived_permission_constants_match_contract() -> None:
    assert CONFIGURATION_VIEW == DEFINITION_VIEW
    assert CONFIGURATION_MANAGE == DEFINITION_MANAGE
    assert HEALTH_VIEW == CATALOG_VIEW
    assert SOD_ACTIONS == ((DEFINITION_MANAGE, DEFINITION_PUBLISH),)


def test_access_requirement_immutability_and_defaults() -> None:
    req = AccessRequirement("perm", "ent", "quota")
    assert req.permission == "perm"
    assert req.entitlement == "ent"
    assert req.quota_resource == "quota"
    assert req.quota_cost == 1

    with pytest.raises(dataclasses.FrozenInstanceError):
        req.quota_cost = 5  # type: ignore[misc]


def test_read_access_helper_specifies_distinct_read_quota() -> None:
    req = read_access("automation_orchestration.definition:view")
    assert req == AccessRequirement(
        permission="automation_orchestration.definition:view",
        entitlement="automation_orchestration.definition:view",
        quota_resource="automation_orchestration.definition:view:read",
        quota_cost=1,
    )


def test_write_access_helper_specifies_state_changing_cost() -> None:
    req_default = write_access("automation_orchestration.run:execute")
    assert req_default == AccessRequirement(
        permission="automation_orchestration.run:execute",
        entitlement="automation_orchestration.run:execute",
        quota_resource="automation_orchestration.run:execute",
        quota_cost=1,
    )

    req_custom = write_access("automation_orchestration.run:execute", cost=3)
    assert req_custom == AccessRequirement(
        permission="automation_orchestration.run:execute",
        entitlement="automation_orchestration.run:execute",
        quota_resource="automation_orchestration.run:execute",
        quota_cost=3,
    )


def test_write_access_helper_enforces_keyword_only_cost() -> None:
    # `cost` is deliberately keyword-only so call sites can never confuse it
    # with a stray positional argument. Passing it positionally must be
    # rejected at the call boundary, not silently accepted.
    with pytest.raises(TypeError):
        write_access("automation_orchestration.run:execute", 3)  # type: ignore[misc]


def test_module_all_exports_exact_public_contract() -> None:
    expected = {
        "AccessRequirement",
        "CATALOG_VIEW",
        "CONFIGURATION_MANAGE",
        "CONFIGURATION_VIEW",
        "DEFINITION_MANAGE",
        "DEFINITION_PUBLISH",
        "DEFINITION_VIEW",
        "HEALTH_VIEW",
        "PERMISSIONS",
        "RUN_CONTROL",
        "RUN_EXECUTE",
        "RUN_RETRY",
        "RUN_VIEW",
        "SCHEDULE_MANAGE",
        "SCHEDULE_VIEW",
        "SOD_ACTIONS",
        "read_access",
        "write_access",
    }
    assert set(permissions_module.__all__) == expected
    assert len(permissions_module.__all__) == len(expected)
    # Every declared export must actually resolve on the module, and every
    # exported name must round-trip to the exact object importers already
    # depend on -- a stale or truncated __all__ silently breaks `from
    # ..permissions import *` without any import-time failure.
    for name in permissions_module.__all__:
        assert hasattr(permissions_module, name), name

    assert permissions_module.CONFIGURATION_VIEW is DEFINITION_VIEW
    assert permissions_module.CONFIGURATION_MANAGE is DEFINITION_MANAGE
    assert permissions_module.HEALTH_VIEW is CATALOG_VIEW


def test_api_uses_standard_csrf_enforcing_session_authentication() -> None:
    assert len(GovernedTenantViewSet.authentication_classes) == 1
    assert issubclass(GovernedTenantViewSet.authentication_classes[0], SessionAuthentication)
    assert all(
        authentication.__name__ != "RelaxedCsrfSessionAuthentication"
        for authentication in GovernedTenantViewSet.authentication_classes
    )
