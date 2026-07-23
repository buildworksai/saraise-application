"""Migration graph, copy policy, table retention and typed RLS evidence."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.special import SeparateDatabaseAndState
from django.db.utils import NotSupportedError

pytest_plugins = ["src.core.testing"]

LEGACY = ("dms", "0002_add_document_models")
LATEST = ("dms", "0007_dms_configuration")
CANONICAL_TABLES = {
    "dms_folders",
    "dms_documents",
    "dms_document_versions",
    "dms_document_permissions",
    "dms_document_shares",
}
LEGACY_TABLES = {f"{table}_legacy" for table in CANONICAL_TABLES} | {"dms_resources_legacy"}


class _Connection:
    def __init__(self, vendor: str) -> None:
        self.vendor = vendor
        self.settings_dict = {"NAME": ":memory:"}


class _SchemaEditor:
    def __init__(self, vendor: str) -> None:
        self.connection = _Connection(vendor)
        self.statements: list[str] = []

    @staticmethod
    def quote_name(value: str) -> str:
        return f'"{value}"'

    def execute(self, sql: str) -> None:
        self.statements.append(sql)


def test_shadow_schema_declares_five_uuid_tenant_models_and_real_constraints() -> None:
    module = importlib.import_module("src.modules.dms.migrations.0003_create_v2_shadow_schema")
    creates = [operation for operation in module.Migration.operations if operation.__class__.__name__ == "CreateModel"]
    assert len(creates) == 5
    assert {operation.options["db_table"] for operation in creates} == {
        "dms_folders_v2",
        "dms_documents_v2",
        "dms_document_versions_v2",
        "dms_document_permissions_v2",
        "dms_document_shares_v2",
    }
    for operation in creates:
        fields = dict(operation.fields)
        assert fields["id"].__class__.__name__ == "UUIDField"
        assert fields["tenant_id"].__class__.__name__ == "UUIDField"
        assert fields["tenant_id"].db_index is True
        assert operation.options["indexes"]
        assert operation.options["constraints"]

    detach = module.Migration.operations[0]
    assert isinstance(detach, SeparateDatabaseAndState)
    assert [operation.__class__.__name__ for operation in detach.state_operations] == ["DeleteModel"]
    assert detach.database_operations[0].reverse_code is not None


def test_copy_and_swap_are_reversible_and_never_use_noop() -> None:
    copy = importlib.import_module("src.modules.dms.migrations.0004_validate_and_copy_legacy_data")
    operation = copy.Migration.operations[0]
    assert operation.reverse_code is copy.delete_copied_shadow_rows
    assert operation.reverse_code.__name__ != "noop"

    swap = importlib.import_module("src.modules.dms.migrations.0005_swap_v2_tables")
    assert len(swap.Migration.operations) == 1
    separated = swap.Migration.operations[0]
    assert isinstance(separated, SeparateDatabaseAndState)
    assert separated.database_operations[0].reverse_code is swap.restore_tables
    assert {legacy for _canonical, _shadow, legacy in swap.TABLES} == {
        "dms_folders_legacy",
        "dms_documents_legacy",
        "dms_document_versions_legacy",
        "dms_document_permissions_legacy",
        "dms_document_shares_legacy",
    }


def test_rls_migration_enforces_each_supported_backend_and_is_fully_reversible() -> None:
    module = importlib.import_module("src.modules.dms.migrations.0006_enable_dms_rls")
    assert set(module.TENANT_TABLES) == CANONICAL_TABLES
    assert ("core", "0011_apply_typed_rls_to_notifications") in module.Migration.dependencies

    postgres = _SchemaEditor("postgresql")
    module.enable_dms_rls(None, postgres)
    assert len(postgres.statements) == 5
    assert all("saraise_enable_rls" in statement and "::REGCLASS" in statement for statement in postgres.statements)
    module.disable_dms_rls(None, postgres)
    reverse_sql = "\n".join(postgres.statements[5:])
    assert reverse_sql.count("DROP POLICY IF EXISTS") == 5
    assert reverse_sql.count("NO FORCE ROW LEVEL SECURITY") == 5
    assert reverse_sql.count("DISABLE ROW LEVEL SECURITY") == 5

    sqlite = _SchemaEditor("sqlite")
    module.enable_dms_rls(None, sqlite)
    forward_sql = "\n".join(sqlite.statements)
    assert forward_sql.count("tenant_id_immutable") == 5
    assert forward_sql.count("same_tenant_insert") == len(module.SQLITE_RELATIONSHIPS)
    assert forward_sql.count("same_tenant_update") == len(module.SQLITE_RELATIONSHIPS)
    module.disable_dms_rls(None, sqlite)
    reverse_start = 5 + (2 * len(module.SQLITE_RELATIONSHIPS))
    reverse_sql = "\n".join(sqlite.statements[reverse_start:])
    assert reverse_sql.count("DROP TRIGGER IF EXISTS") == 5 + (2 * len(module.SQLITE_RELATIONSHIPS))


def test_rls_migration_fails_closed_for_unsupported_database_backends() -> None:
    module = importlib.import_module("src.modules.dms.migrations.0006_enable_dms_rls")

    unsupported = _SchemaEditor("mysql")
    with pytest.raises(NotSupportedError, match="requires PostgreSQL"):
        module.enable_dms_rls(None, unsupported)
    with pytest.raises(NotSupportedError, match="requires PostgreSQL"):
        module.disable_dms_rls(None, unsupported)
    assert unsupported.statements == []


def test_sqlite_isolation_guards_require_the_explicit_in_memory_test_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("src.modules.dms.migrations.0006_enable_dms_rls")
    monkeypatch.delenv(module.SQLITE_TEST_ENVIRONMENT, raising=False)

    sqlite = _SchemaEditor("sqlite")
    with pytest.raises(NotSupportedError, match="requires PostgreSQL"):
        module.enable_dms_rls(None, sqlite)
    assert sqlite.statements == []


@pytest.mark.django_db(transaction=True)
def test_empty_schema_reverses_to_v1_and_forwards_again() -> None:
    """Exercise database and state reversals on every supported test backend."""

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    legacy_tables = set(connection.introspection.table_names())
    assert CANONICAL_TABLES | {"dms_resources"} <= legacy_tables
    assert not LEGACY_TABLES.intersection(legacy_tables)

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    latest_tables = set(connection.introspection.table_names())
    assert CANONICAL_TABLES | LEGACY_TABLES <= latest_tables
    final_apps = executor.loader.project_state([LATEST]).apps
    Folder = final_apps.get_model("dms", "Folder")
    assert final_apps.get_model("dms", "Document")._meta.get_field("tenant_id").get_internal_type() == "UUIDField"

    if connection.vendor == "sqlite":
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        actor_id = uuid.uuid4()
        folder_a = Folder.objects.create(
            tenant_id=tenant_a,
            name="Tenant A",
            path="tenant-a",
            created_by=actor_id,
        )
        folder_b = Folder.objects.create(
            tenant_id=tenant_b,
            name="Tenant B",
            path="tenant-b",
            created_by=actor_id,
        )
        with pytest.raises(IntegrityError, match="tenant ownership is immutable"), transaction.atomic():
            Folder.objects.filter(pk=folder_a.pk).update(tenant_id=tenant_b)
        folder_a.refresh_from_db()
        assert folder_a.tenant_id == tenant_a

        with pytest.raises(IntegrityError, match="crosses tenant boundary"), transaction.atomic():
            Folder.objects.create(
                tenant_id=tenant_a,
                name="Forbidden child",
                parent=folder_b,
                path="tenant-b/forbidden",
                depth=1,
                created_by=actor_id,
            )
        assert not Folder.objects.filter(tenant_id=tenant_a, parent=folder_b).exists()


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_17_forward_reverse_forward_preserves_rows_and_references() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL 17 migration acceptance runs in the PostgreSQL gate")
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        assert int(cursor.fetchone()[0]) >= 170000

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    legacy_apps = executor.loader.project_state([LEGACY]).apps
    Folder = legacy_apps.get_model("dms", "Folder")
    Document = legacy_apps.get_model("dms", "Document")
    Version = legacy_apps.get_model("dms", "DocumentVersion")
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    storage_key = f"tenants/{tenant_id}/legacy/{version_id}"
    folder = Folder.objects.create(
        id=str(folder_id), tenant_id=str(tenant_id), name="Evidence", path="", created_by=str(actor_id)
    )
    document = Document.objects.create(
        id=str(document_id),
        tenant_id=str(tenant_id),
        folder=folder,
        name="evidence.pdf",
        file_path=storage_key,
        mime_type="application/pdf",
        size=128,
        checksum="a" * 64,
        created_by=str(actor_id),
    )
    Version.objects.create(
        id=str(version_id),
        document=document,
        version_number=1,
        file_path=storage_key,
        created_by=str(actor_id),
    )

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    tables = set(connection.introspection.table_names())
    assert CANONICAL_TABLES | LEGACY_TABLES <= tables
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])
        cursor.execute(
            "SELECT storage_key, checksum_sha256, document_id, tenant_id " "FROM dms_document_versions WHERE id = %s",
            [str(version_id)],
        )
        assert cursor.fetchone() == (storage_key, "a" * 64, document_id, tenant_id)
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.polqual IS NOT NULL, p.polwithcheck IS NOT NULL
              FROM pg_class c
              JOIN pg_policy p ON p.polrelid = c.oid
             WHERE c.relname = ANY(%s)
            """,
            [list(CANONICAL_TABLES)],
        )
        assert len(cursor.fetchall()) == 5

    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    assert CANONICAL_TABLES <= set(connection.introspection.table_names())
    legacy_state = executor.loader.project_state([LEGACY]).apps
    assert legacy_state.get_model("dms", "Document").objects.filter(pk=str(document_id)).exists()

    executor = MigrationExecutor(connection)
    executor.migrate([LATEST])
    final_state = executor.loader.project_state([LATEST]).apps
    migrated = final_state.get_model("dms", "DocumentVersion").objects.get(pk=version_id)
    assert migrated.storage_key == storage_key
    assert migrated.checksum_sha256 == "a" * 64


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_invalid_uuid_aborts_before_copy_and_can_be_remediated() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL migration failure/recovery runs in the PostgreSQL gate")
    executor = MigrationExecutor(connection)
    executor.migrate([LEGACY])
    apps = executor.loader.project_state([LEGACY]).apps
    Folder = apps.get_model("dms", "Folder")
    bad = Folder.objects.create(
        id=str(uuid.uuid4()), tenant_id="not-a-uuid", name="Bad", path="", created_by=str(uuid.uuid4())
    )
    executor = MigrationExecutor(connection)
    with pytest.raises(RuntimeError, match="tenant_id is not a UUID"):
        executor.migrate([("dms", "0004_validate_and_copy_legacy_data")])

    executor = MigrationExecutor(connection)
    state = executor.loader.project_state([("dms", "0003_create_v2_shadow_schema")]).apps
    state.get_model("dms", "Folder").objects.filter(pk=bad.pk).delete()
    executor.migrate([LATEST])
