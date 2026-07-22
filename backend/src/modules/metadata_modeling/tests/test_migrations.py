"""Migration-chain reversibility and final-state contract checks."""

import importlib

import pytest
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor

pytest_plugins = ["src.core.testing.factories"]


def test_data_and_rls_migrations_declare_real_reverse_operations():
    backfill = importlib.import_module("src.modules.metadata_modeling.migrations.0004_backfill_schema_versions")
    security = importlib.import_module("src.modules.metadata_modeling.migrations.0006_metadata_modeling_rls")
    backfill_operation = backfill.Migration.operations[0]
    security_operation = security.Migration.operations[0]
    assert isinstance(backfill_operation, migrations.RunPython)
    assert backfill_operation.reverse_code is backfill.reverse_schema_versions
    assert isinstance(security_operation, migrations.RunPython)
    assert security_operation.reverse_code is security.remove_security
    assert len(security.TABLES) == 8


@pytest.mark.django_db(transaction=True)
def test_latest_migration_state_contains_indexed_uuid_tenant_columns():
    executor = MigrationExecutor(connection)
    state = executor.loader.project_state(("metadata_modeling", "0006_metadata_modeling_rls"))
    for model_name in (
        "entitydefinition",
        "entityschemaversion",
        "fielddefinition",
        "dynamicresource",
        "dynamicresourceversion",
        "namingsequence",
        "metadatamodelingconfiguration",
        "metadataconfigurationaudit",
    ):
        field = state.models["metadata_modeling", model_name].fields["tenant_id"]
        assert field.get_internal_type() == "UUIDField"
        assert field.db_index is True
