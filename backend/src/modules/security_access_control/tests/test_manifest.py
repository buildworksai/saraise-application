from pathlib import Path

from src.core.module_manifest_schema import ModuleLifecycle, ModuleType, manifest_validator


def test_security_manifest_is_schema_valid_and_declares_complete_governance_contract() -> None:
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = manifest_validator.validate_from_yaml(path.read_text(encoding="utf-8"))

    assert manifest.name == "security-access-control"
    assert manifest.type == ModuleType.FOUNDATION
    assert manifest.lifecycle == ModuleLifecycle.CORE
    assert manifest.dependencies == ["core-identity >=1.0.0"]
    required_permissions = {
        f"security.{resource}:{action}"
        for resource, actions in {
            "roles": ("create", "read", "update", "delete"),
            "assignments": ("create", "read", "update", "delete"),
            "permission-sets": ("create", "read", "update", "delete"),
            "field-security": ("create", "read", "update", "delete"),
            "row-security": ("create", "read", "update", "delete"),
            "security-profiles": ("create", "read", "update", "delete"),
            "permissions": ("read",),
            "audit-logs": ("read",),
            "access": ("simulate",),
        }.items()
        for action in actions
    }
    assert set(manifest.permissions) == required_permissions
    assert set(manifest.sod_actions) == {
        "security.roles:delete",
        "security.security-profiles:update",
    }
    assert manifest.ai_tools == []
    assert manifest.metadata["policy_ownership"] == {
        "development": "local",
        "self-hosted": "local",
        "saas": "remote",
    }
    assert manifest.metadata["remote_policy_dependency"]["key"] == "policy-engine"
    assert manifest.metadata["remote_policy_dependency"]["fail_closed"] is True
    assert manifest.metadata["extension_contract"] == {
        "schema_version": "1.0",
        "public_import": "src.modules.security_access_control.extensions",
        "permission_catalog": {"namespace": "security", "ownership": "manifest"},
        "resource_security": {"descriptors": "field-metadata", "namespace_ownership": "manifest"},
        "row_policy": {"schema": "safe-predicate", "schema_version": "1.0"},
    }
