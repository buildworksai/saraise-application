"""Tenant configuration validation, versioning and isolation proofs."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import Group

from src.core.access.entitlements import Quota
from src.modules.dms.managers import ImmutableVersionError
from src.modules.dms.models import DmsConfiguration, DmsConfigurationAudit, DmsConfigurationVersion
from src.modules.dms.services import (
    DEFAULT_DMS_CONFIGURATION,
    DmsConfigurationService,
    DmsIntegrityFailure,
    DmsPermissionDenied,
    DmsValidationError,
    _normalize_metadata,
    _normalize_name,
    _normalize_tags,
    _policy_dict,
    _policy_int,
    _policy_string_sequence,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


def test_configuration_is_tenant_scoped_versioned_audited_and_reversible() -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    actor_a, actor_b = uuid.uuid4(), uuid.uuid4()

    initial_a = DmsConfigurationService.current(tenant_a, actor_a)
    initial_b = DmsConfigurationService.current(tenant_b, actor_b)
    assert initial_a.values == DEFAULT_DMS_CONFIGURATION
    assert initial_a.values["forbidden_name_characters"] == ["/", "\\u0000"]
    with pytest.raises(DmsValidationError):
        _normalize_name("bad\u0000name", tenant_id=tenant_a)
    assert initial_b.values == DEFAULT_DMS_CONFIGURATION
    assert DmsConfiguration.objects.filter(tenant_id=tenant_a).get() == initial_a
    assert not DmsConfiguration.objects.filter(tenant_id=tenant_a, id=initial_b.id).exists()

    changed = dict(initial_a.values)
    changed["max_document_tags"] = 75
    preview = DmsConfigurationService.preview(tenant_a, actor_a, changed)
    assert preview["valid"] is True
    assert preview["changes"] == [{"field": "max_document_tags", "before": 50, "after": 75}]

    updated = DmsConfigurationService.update(tenant_a, actor_a, changed)
    assert updated.version == 2
    assert DmsConfigurationService.runtime_values(tenant_a)["max_document_tags"] == 75
    assert list(DmsConfigurationService.history(tenant_a, actor_a).values_list("version", flat=True)) == [2, 1]
    audit = list(DmsConfigurationService.audit(tenant_a, actor_a))
    assert [row.action for row in audit] == ["updated", "created"]
    assert all(row.correlation_id for row in audit)
    assert all(row.tenant_id == tenant_a for row in audit)
    assert not DmsConfigurationVersion.objects.filter(tenant_id=tenant_a, configuration=initial_b).exists()
    assert not DmsConfigurationAudit.objects.filter(tenant_id=tenant_a, configuration=initial_b).exists()
    projected_quota = Quota.objects.get(tenant_id=tenant_a, resource="dms.api_reads")
    assert projected_quota.limit == changed["api_read_quota"]
    assert projected_quota.remaining == changed["api_read_quota"]
    assert projected_quota.metadata["configuration_version"] == 2

    rolled_back = DmsConfigurationService.rollback(tenant_a, actor_a, 1)
    assert rolled_back.version == 3
    assert rolled_back.values["max_document_tags"] == 50
    assert DmsConfigurationService.current(tenant_b, actor_b).version == 1


def test_configuration_import_export_validation_and_immutable_evidence() -> None:
    tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()
    current = DmsConfigurationService.current(tenant_id, actor_id)
    document = DmsConfigurationService.export_document(tenant_id, actor_id)
    values = dict(document["values"])
    values["default_share_access_count"] = 11
    document["values"] = values
    imported = DmsConfigurationService.import_document(tenant_id, actor_id, document)
    assert imported.version == 2
    assert imported.values["default_share_access_count"] == 11
    wrong_module = dict(document)
    wrong_module["module"] = "another-module"
    with pytest.raises(DmsValidationError):
        DmsConfigurationService.import_document(tenant_id, actor_id, wrong_module)
    extra_field = dict(document)
    extra_field["unexpected"] = "not part of the portable configuration schema"
    with pytest.raises(DmsValidationError, match="Unsupported configuration document schema"):
        DmsConfigurationService.import_document(tenant_id, actor_id, extra_field)
    list_values = dict(document)
    list_values["values"] = []
    with pytest.raises(DmsValidationError) as list_values_error:
        DmsConfigurationService.import_document(tenant_id, actor_id, list_values)
    assert list_values_error.value.args == ("Unsupported configuration document schema.",)
    assert list_values_error.value.detail == {"non_field_errors": ["Unsupported configuration document schema."]}

    invalid = dict(imported.values)
    invalid["max_folder_depth"] = 65
    with pytest.raises(DmsValidationError):
        DmsConfigurationService.update(tenant_id, actor_id, invalid)
    current.refresh_from_db()
    assert current.version == 2

    version = DmsConfigurationVersion.objects.filter(tenant_id=tenant_id).first()
    audit = DmsConfigurationAudit.objects.filter(tenant_id=tenant_id).first()
    assert version is not None and audit is not None
    with pytest.raises(ImmutableVersionError):
        DmsConfigurationVersion.objects.filter(id=version.id).update(values={})
    with pytest.raises(ImmutableVersionError):
        audit.delete()


def test_configuration_validation_rejects_non_finite_numbers_and_allows_equal_boundaries() -> None:
    non_finite = dict(DEFAULT_DMS_CONFIGURATION)
    non_finite["max_folder_depth"] = float("nan")
    with pytest.raises(ValueError):
        DmsConfigurationService.validate_values(non_finite)

    equal_boundaries = dict(DEFAULT_DMS_CONFIGURATION)
    equal_boundaries["principal_search_min_limit"] = 20
    equal_boundaries["principal_search_default_limit"] = 20
    equal_boundaries["principal_search_max_limit"] = 20
    equal_boundaries["principal_query_min_length"] = 100
    equal_boundaries["principal_query_max_length"] = 100
    equal_boundaries["default_share_access_count"] = 10_000
    equal_boundaries["max_share_access_count"] = 10_000
    equal_boundaries["folder_page_size"] = 100
    equal_boundaries["document_page_size"] = 100
    equal_boundaries["max_page_size"] = 100

    validated = DmsConfigurationService.validate_values(equal_boundaries)

    assert validated["principal_search_default_limit"] == 20
    assert validated["principal_query_max_length"] == 100
    assert validated["default_share_access_count"] == 10_000
    assert validated["folder_page_size"] == 100
    assert validated["document_page_size"] == 100
    assert validated["max_page_size"] == 100


def test_configuration_runtime_defaults_environment_and_shape_fail_closed() -> None:
    defaults = DmsConfigurationService.runtime_values(None)
    assert defaults == DEFAULT_DMS_CONFIGURATION
    defaults["max_folder_depth"] = 1
    assert DEFAULT_DMS_CONFIGURATION["max_folder_depth"] == 10

    assert DmsConfigurationService.validate_environment(" Staging_1 ") == "staging_1"
    for invalid in ("", "not valid", "x" * 65):
        with pytest.raises(DmsValidationError, match="bounded slug"):
            DmsConfigurationService.validate_environment(invalid)

    with pytest.raises(DmsValidationError) as non_object:
        DmsConfigurationService.validate_values([])
    assert non_object.value.detail == {"non_field_errors": ["Configuration values must be an object."]}

    missing = dict(DEFAULT_DMS_CONFIGURATION)
    missing.pop("max_folder_depth")
    with pytest.raises(DmsValidationError) as missing_error:
        DmsConfigurationService.validate_values(missing)
    assert "missing_fields" in missing_error.value.detail

    unknown = dict(DEFAULT_DMS_CONFIGURATION, unsafe_policy=True)
    with pytest.raises(DmsValidationError) as unknown_error:
        DmsConfigurationService.validate_values(unknown)
    assert "unknown_fields" in unknown_error.value.detail

    assert DmsConfigurationService.forbidden_name_characters({"forbidden_name_characters": "/"}) == ()


def test_configuration_validation_reports_compound_policy_shape_errors() -> None:
    invalid = dict(DEFAULT_DMS_CONFIGURATION)
    invalid.update(
        {
            "principal_search_min_limit": 30,
            "principal_search_default_limit": 20,
            "principal_search_max_limit": 10,
            "principal_query_min_length": 20,
            "principal_query_max_length": 10,
            "default_share_access_count": 20,
            "max_share_access_count": 10,
            "folder_page_size": 80,
            "document_page_size": 90,
            "max_page_size": 70,
            "permission_implications": {"read": ["read"]},
            "forbidden_name_characters": ["/"],
            "document_ordering_fields": ["name"],
            "default_document_ordering": "-updated_at",
            "blocked_file_signatures": ["not-hex"],
            "permitted_mime_types": ["text plain"],
            "executable_extensions": ["EXE"],
            "folder_deletion_policy": "delete_all",
            "storage_backend": "s3",
            "restore_note_template": "Restored",
            "governance_required_operations": ["format"],
            "feature_flags": {"uploads": "yes"},
            "rollout": {"enabled": True, "roles": "admins", "cohorts": []},
        }
    )

    with pytest.raises(DmsValidationError) as exc_info:
        DmsConfigurationService.validate_values(invalid)

    detail = exc_info.value.detail
    assert detail["principal_search_default_limit"] == ["Must not exceed principal_search_max_limit."]
    assert detail["principal_query_max_length"] == ["Must not be below principal_query_min_length."]
    assert detail["default_share_access_count"] == ["Must not exceed max_share_access_count."]
    assert detail["max_page_size"] == ["Must be at least both configured page sizes."]
    assert "permission_implications" in detail
    assert "forbidden_name_characters" in detail
    assert "document_ordering_fields" in detail
    assert "blocked_file_signatures" in detail
    assert "permitted_mime_types" in detail
    assert "executable_extensions" in detail
    assert "folder_deletion_policy" in detail
    assert "storage_backend" in detail
    assert "restore_note_template" in detail
    assert "governance_required_operations" in detail
    assert "feature_flags" in detail
    assert "rollout" in detail


def test_runtime_policy_helpers_fail_closed_on_corrupt_validated_document() -> None:
    with pytest.raises(DmsIntegrityFailure, match="validated integer"):
        _policy_int({"max_name_length": True}, "max_name_length")

    with pytest.raises(DmsIntegrityFailure) as object_error:
        _policy_dict({"feature_flags": []}, "feature_flags")
    assert object_error.value.args == ("DMS policy field feature_flags is not a validated object.",)

    with pytest.raises(DmsIntegrityFailure) as sequence_error:
        _policy_string_sequence({"forbidden_name_characters": "/"}, "forbidden_name_characters")
    assert sequence_error.value.args == ("DMS policy field forbidden_name_characters is not a validated string list.",)

    with pytest.raises(DmsIntegrityFailure) as non_string_error:
        _policy_string_sequence({"forbidden_name_characters": ["/", 0]}, "forbidden_name_characters")
    assert non_string_error.value.args == ("DMS policy field forbidden_name_characters contains a non-string value.",)


def test_metadata_and_tag_normalizers_enforce_configured_safety_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()

    assert _normalize_tags([" Legal ", "legal", "2026"], tenant_id=tenant_id) == ["legal", "2026"]
    with pytest.raises(DmsValidationError, match="Tags must be strings"):
        _normalize_tags(["legal", 2026], tenant_id=tenant_id)
    with pytest.raises(DmsValidationError, match="Tag is invalid"):
        _normalize_tags([""], tenant_id=tenant_id)

    values = dict(DEFAULT_DMS_CONFIGURATION, max_metadata_key_length=3, max_metadata_bytes=1024, max_name_length=3)
    monkeypatch.setattr(DmsConfigurationService, "runtime_values", staticmethod(lambda _tenant_id: values))

    assert _normalize_name(" abc ", tenant_id=tenant_id) == "abc"
    with pytest.raises(DmsValidationError, match="read-only"):
        _normalize_metadata({"_extensions": {}}, tenant_id=tenant_id)
    with pytest.raises(DmsValidationError, match="bounded strings"):
        _normalize_metadata({"long": "x"}, tenant_id=tenant_id)
    with pytest.raises(DmsValidationError, match="non-finite"):
        _normalize_metadata({"nan": float("nan")}, tenant_id=tenant_id)
    with pytest.raises(DmsValidationError, match="unsupported JSON value"):
        _normalize_metadata({"bad": object()}, tenant_id=tenant_id)
    with pytest.raises(DmsValidationError, match="too large"):
        _normalize_metadata({"abc": "x" * 1100}, tenant_id=tenant_id)


def test_feature_rollout_uses_server_owned_tenant_roles(tenant_a_user) -> None:
    tenant_a_user.profile.refresh_from_db()
    tenant_id = tenant_a_user.profile.tenant_id
    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{tenant_a_user.id}")
    configuration = DmsConfigurationService.current(tenant_id, actor_id)
    values = dict(configuration.values)
    values["rollout"] = {
        "enabled": True,
        "roles": ["tenant_admin"],
        "cohorts": [],
    }
    DmsConfigurationService.update(tenant_id, actor_id, values)

    DmsConfigurationService.require_feature(tenant_id, actor_id, "uploads")
    with pytest.raises(DmsPermissionDenied):
        DmsConfigurationService.require_feature(tenant_id, uuid.uuid4(), "uploads")

    cohort = Group.objects.create(name="dms-pilot")
    tenant_a_user.groups.add(cohort)
    values["rollout"] = {
        "enabled": True,
        "roles": [],
        "cohorts": ["dms-pilot"],
    }
    DmsConfigurationService.update(tenant_id, actor_id, values)

    DmsConfigurationService.require_feature(tenant_id, actor_id, "uploads")


@pytest.mark.parametrize(
    "rollout",
    [
        {"enabled": True, "roles": "tenant_admin", "cohorts": []},
        {"enabled": True, "roles": [], "cohorts": "dms-pilot"},
    ],
)
def test_feature_rollout_rejects_malformed_runtime_role_and_cohort_policy(
    monkeypatch: pytest.MonkeyPatch, rollout: dict[str, object]
) -> None:
    monkeypatch.setattr(
        DmsConfigurationService,
        "runtime_values",
        staticmethod(
            lambda tenant_id: {
                "feature_flags": {"uploads": True},
                "rollout": rollout,
            }
        ),
    )

    with pytest.raises(DmsIntegrityFailure):
        DmsConfigurationService.require_feature(uuid.uuid4(), uuid.uuid4(), "uploads")
