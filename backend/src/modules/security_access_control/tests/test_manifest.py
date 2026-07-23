from pathlib import Path

from django.apps import apps

from src.core.module_manifest_schema import ModuleLifecycle, ModuleType, manifest_validator
from src.modules.security_access_control.urls import router


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
            "configuration": ("read", "update"),
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


def test_manifest_inventory_matches_models_router_actions_methods_and_permissions() -> None:
    path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = manifest_validator.validate_from_yaml(path.read_text(encoding="utf-8"))

    entity_inventory = {item["model"]: item for item in manifest.metadata["entity_inventory"]}
    concrete_models = {model.__name__: model for model in apps.get_app_config("security_access_control").get_models()}
    assert set(entity_inventory) == set(concrete_models)
    for model_name, model in concrete_models.items():
        declaration = entity_inventory[model_name]
        assert declaration["table"] == model._meta.db_table
        expected_ownership = "tenant" if any(field.name == "tenant_id" for field in model._meta.fields) else "global"
        assert declaration["ownership"] == expected_ownership

    resources = {item["prefix"]: item for item in manifest.metadata["api_inventory"]["resources"]}
    registered = {prefix: (viewset, basename) for prefix, viewset, basename in router.registry}
    assert set(resources) == set(registered)

    standard_methods = {
        "list": "GET",
        "retrieve": "GET",
        "create": "POST",
        "partial_update": "PATCH",
        "destroy": "DELETE",
        "retrieve_current": "GET",
        "update_current": "PUT",
    }
    declared_permissions = set(manifest.permissions)
    for prefix, (viewset, basename) in registered.items():
        declaration = resources[prefix]
        assert declaration["basename"] == basename
        assert declaration["viewset"] == viewset.__name__
        assert declaration["ownership"] in {"tenant", "global-catalog"}
        actions = declaration["actions"]
        assert set(actions) == set(viewset.permission_map)
        for action_name, permission in viewset.permission_map.items():
            action = actions[action_name]
            assert action["permission"] == permission
            assert permission in declared_permissions
            method = action["method"]
            assert method in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            assert isinstance(action["path"], str)
            view_method = getattr(viewset, action_name)
            mapping = getattr(view_method, "mapping", None)
            if mapping is None:
                assert standard_methods[action_name] == method
            else:
                assert mapping[method.lower()] == action_name
