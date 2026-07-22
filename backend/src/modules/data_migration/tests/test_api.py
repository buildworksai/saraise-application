"""Governed API v2 route, boundary and service-delegation contracts."""

from __future__ import annotations

import inspect

import pytest
from django.urls import resolve
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.modules.data_migration import api


@pytest.mark.parametrize(
    ("path", "view_name"),
    (
        ("/api/v2/data-migration/jobs/", "data_migration:job-list"),
        ("/api/v2/data-migration/jobs/import/", "data_migration:job-import-definition"),
        ("/api/v2/data-migration/jobs/00000000-0000-0000-0000-000000000001/validate/", "data_migration:job-validate-definition"),
        ("/api/v2/data-migration/jobs/00000000-0000-0000-0000-000000000001/dry-runs/", "data_migration:job-request-dry-run"),
        ("/api/v2/data-migration/runs/00000000-0000-0000-0000-000000000001/issues/export/", "data_migration:run-export-issues"),
        ("/api/v2/data-migration/connections/00000000-0000-0000-0000-000000000001/test/", "data_migration:connection-test-connection"),
        ("/api/v2/data-migration/configuration/", "data_migration:configuration"),
        ("/api/v2/data-migration/configuration/versions/1/restore/", "data_migration:configuration-restore"),
        ("/api/v2/data-migration/health/live/", "data_migration:health-live"),
        ("/api/v2/data-migration/health/ready/", "data_migration:health-ready"),
    ),
)
def test_required_routes_resolve(path: str, view_name: str) -> None:
    assert resolve(path).view_name == view_name


@pytest.mark.parametrize(
    "viewset",
    (
        api.MigrationJobViewSet, api.MigrationMappingViewSet, api.ValidationRuleViewSet,
        api.MigrationRunViewSet, api.MigrationRollbackViewSet, api.ExternalConnectionViewSet,
        api.DataMigrationConfigurationViewSet,
    ),
)
def test_every_json_viewset_uses_governed_profile_and_bounded_pagination(viewset: type) -> None:
    assert issubclass(viewset, GovernedAPIViewMixin)
    assert viewset.pagination_class is GovernedPageNumberPagination


@pytest.mark.parametrize(
    ("viewset", "method", "service_name"),
    (
        (api.MigrationJobViewSet, "create", "MigrationJobService.create"),
        (api.MigrationJobViewSet, "partial_update", "MigrationJobService.update"),
        (api.MigrationJobViewSet, "destroy", "MigrationJobService.soft_delete"),
        (api.MigrationMappingViewSet, "partial_update", "MigrationMappingService.update"),
        (api.ValidationRuleViewSet, "partial_update", "ValidationRuleService.update"),
        (api.MigrationRunViewSet, "cancel", "MigrationExecutionService.cancel"),
        (api.MigrationRunViewSet, "rollback", "RollbackService.request"),
        (api.ExternalConnectionViewSet, "create", "ExternalConnectionService.register"),
        (api.DataMigrationConfigurationViewSet, "update_configuration", "DataMigrationConfigurationService.update"),
    ),
)
def test_mutations_delegate_to_services(viewset: type, method: str, service_name: str) -> None:
    source = inspect.getsource(getattr(viewset, method))
    assert service_name in source
    assert ".save(" not in source
    assert ".objects.create(" not in source


def test_idempotency_key_is_mandatory_and_validated() -> None:
    missing = APIRequestFactory().post("/api/v2/data-migration/jobs/id/runs/")
    with pytest.raises(ValidationError):
        api._idempotency_key(missing)
    valid = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="tenant:run:001")
    assert api._idempotency_key(valid) == "tenant:run:001"
    oversized = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="x" * 256)
    with pytest.raises(ValidationError):
        api._idempotency_key(oversized)


def test_csv_formula_injection_is_neutralized() -> None:
    for unsafe in ("=cmd()", "+1", "-1", "@SUM(A1)", "\tformula", "\rformula"):
        assert api._csv_cell(unsafe).startswith("'")
    assert api._csv_cell("ordinary") == "ordinary"
