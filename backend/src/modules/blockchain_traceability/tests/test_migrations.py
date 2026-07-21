"""Legacy preservation, reversible schema, constraints, and PostgreSQL RLS."""

from __future__ import annotations

import importlib
import json
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

LEGACY = ("blockchain_traceability", "0001_initial")
LATEST = ("blockchain_traceability", "0004_domain_rls")
LEGACY_TABLE = "blockchain_traceability_resources"
DOMAIN_TABLES = {
    "blockchain_traceability_ledger_networks",
    "blockchain_traceability_assets",
    "blockchain_traceability_events",
    "blockchain_traceability_ledger_anchors",
    "blockchain_traceability_authenticity_credentials",
    "blockchain_traceability_compliance_evidence",
    "blockchain_traceability_verification_attempts",
}


def _tables() -> set[str]:
    return set(connection.introspection.table_names())


def _legacy_snapshot(identifier: str) -> tuple[object, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT id, tenant_id, name, description, is_active, config, created_by FROM "{LEGACY_TABLE}" WHERE id = %s',
            [identifier],
        )
        row = cursor.fetchone()
    assert row is not None
    return row


@pytest.mark.django_db(transaction=True)
def test_forward_reverse_forward_preserves_legacy_bytes_and_domain_tables() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    legacy_apps = executor.loader.project_state([LEGACY]).apps
    LegacyResource = legacy_apps.get_model("blockchain_traceability", "BlockchainTraceabilityResource")
    identifier = str(uuid.uuid4())
    LegacyResource.objects.create(
        id=identifier,
        tenant_id=str(uuid.uuid4()),
        name="Opaque legacy resource",
        description="Never infer ledger evidence",
        is_active=True,
        config={"arbitrary": [1, "two", {"untrusted": True}]},
        created_by=str(uuid.uuid4()),
    )
    original = _legacy_snapshot(identifier)

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    latest_apps = executor.loader.project_state([LATEST]).apps
    latest_names = {
        model.__name__ for model in latest_apps.get_models() if model._meta.app_label == "blockchain_traceability"
    }
    assert "LegacyBlockchainTraceabilityResource" not in latest_names
    assert DOMAIN_TABLES <= _tables() and LEGACY_TABLE in _tables()
    assert _legacy_snapshot(identifier) == original

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    assert DOMAIN_TABLES.isdisjoint(_tables()) and LEGACY_TABLE in _tables()
    assert _legacy_snapshot(identifier) == original

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    assert DOMAIN_TABLES <= _tables()
    assert _legacy_snapshot(identifier) == original


def test_quarantine_renames_state_only_and_has_real_reverse() -> None:
    module = importlib.import_module(
        "src.modules.blockchain_traceability.migrations.0002_quarantine_legacy_resource"
    )
    operation = module.Migration.operations[0]
    assert operation.__class__.__name__ == "SeparateDatabaseAndState"
    assert [item.__class__.__name__ for item in operation.state_operations] == ["RenameModel"]
    run_python = operation.database_operations[0]
    assert run_python.reverse_code is not None


def test_domain_migration_declares_exact_tables_uuid_tenants_constraints_and_reversal() -> None:
    module = importlib.import_module("src.modules.blockchain_traceability.migrations.0003_domain_schema")
    creates = [operation for operation in module.Migration.operations if operation.__class__.__name__ == "CreateModel"]
    assert len(creates) == 7
    assert {operation.options["db_table"] for operation in creates} == DOMAIN_TABLES
    for operation in creates:
        tenant_field = dict(operation.fields)["tenant_id"]
        assert tenant_field.__class__.__name__ == "UUIDField" and tenant_field.db_index is True
    constraints = [
        operation
        for operation in module.Migration.operations
        if operation.__class__.__name__ == "AddConstraint"
    ]
    names = {operation.constraint.name for operation in constraints}
    assert {
        "bct_verify_required_target",
        "bct_verify_verified_evidence",
        "bct_verify_simulated_inconclusive",
        "bct_event_asset_sequence_uniq",
        "bct_anchor_confirmed_has_evidence",
    } <= names
    detached = [
        operation
        for operation in module.Migration.operations
        if operation.__class__.__name__ == "SeparateDatabaseAndState"
    ]
    assert len(detached) == 1 and detached[0].database_operations == []


def test_rls_migration_covers_exact_tables_and_typed_core_dependency() -> None:
    module = importlib.import_module("src.modules.blockchain_traceability.migrations.0004_domain_rls")
    assert set(module.DOMAIN_TABLES) == DOMAIN_TABLES
    assert ("core", "0011_apply_typed_rls_to_notifications") in module.Migration.dependencies
    operation = module.Migration.operations[0]
    assert operation.reverse_code is not None


def test_manifest_is_validator_compatible_and_declares_extension_contract() -> None:
    import yaml

    from src.core.module_manifest_schema import manifest_validator

    path = __file__.replace("tests/test_migrations.py", "manifest.yaml")
    manifest = manifest_validator.validate_from_yaml(open(path, encoding="utf-8").read())
    data = yaml.safe_load(open(path, encoding="utf-8"))
    assert manifest.version == "2.0.0" and len(manifest.permissions) == 27
    assert data["metadata"]["durable_job_commands"] == ["blockchain_traceability.submit_anchor"]
    assert len(data["metadata"]["domain_events"]) == 10
    assert len(data["metadata"]["extension_points"]) == 4
    json.dumps(data, sort_keys=True)


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgresql
def test_postgresql_force_rls_and_non_owner_crud_isolation() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL RLS execution runs in the dedicated PostgreSQL gate")
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    role = f"bct_rls_{uuid.uuid4().hex[:10]}"
    role_q = connection.ops.quote_name(role)
    table = "blockchain_traceability_assets"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
              FROM pg_class c JOIN pg_policy p ON p.polrelid = c.oid
             WHERE c.relname = ANY(%s)
            """,
            [list(DOMAIN_TABLES)],
        )
        rows = cursor.fetchall()
        assert len(rows) == 7 and all(enabled and forced and using and checking for _, enabled, forced, using, checking in rows)
        cursor.execute(f"CREATE ROLE {role_q} NOLOGIN")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role_q}")
        try:
            cursor.execute(f"SET LOCAL ROLE {role_q}")
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
            cursor.execute(
                f"""
                INSERT INTO {table}
                  (id, tenant_id, created_at, updated_at, created_by, updated_by, is_deleted,
                   deleted_by, asset_key, name, description, product_ref, batch_ref,
                   serial_number, gtin, asset_type, status, attributes, head_sequence,
                   head_hash, transition_history)
                VALUES (%s, %s, NOW(), NOW(), 'rls-user', '', FALSE, '', 'rls-a', 'RLS asset', '', '', '',
                        'SERIAL-RLS', '', 'test', 'draft', '{{}}', 0, '', '[]')
                """,
                [str(uuid.uuid4()), str(tenant_a)],
            )
            with pytest.raises(Exception):
                cursor.execute(
                    f"""
                    INSERT INTO {table}
                      (id, tenant_id, created_at, updated_at, created_by, updated_by, is_deleted,
                       deleted_by, asset_key, name, description, product_ref, batch_ref,
                       serial_number, gtin, asset_type, status, attributes, head_sequence,
                       head_hash, transition_history)
                    VALUES (%s, %s, NOW(), NOW(), 'rls-user', '', FALSE, '', 'rls-b', 'Foreign', '', '', '',
                            'SERIAL-B', '', 'test', 'draft', '{{}}', 0, '', '[]')
                    """,
                    [str(uuid.uuid4()), str(tenant_b)],
                )
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP ROLE IF EXISTS {role_q}")
