"""End-to-end and unit tests for typed PostgreSQL tenant RLS."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse

from src.core.middleware.tenant_context import TenantContextMiddleware
from src.core.tenancy.rls import (
    InvalidTenantContext,
    MissingTenantContext,
    get_current_tenant_id,
    tenant_context,
    tenant_context_worker,
)


def test_tenant_context_is_typed_and_nested_on_sqlite():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    assert get_current_tenant_id() is None
    with tenant_context(str(tenant_a)) as current_a:
        assert current_a == tenant_a
        assert get_current_tenant_id() == tenant_a
        with tenant_context(tenant_b):
            assert get_current_tenant_id() == tenant_b
        assert get_current_tenant_id() == tenant_a
    assert get_current_tenant_id() is None


def test_tenant_context_rejects_malformed_uuid():
    with pytest.raises(InvalidTenantContext, match="valid UUID"):
        with tenant_context("not-a-tenant"):
            pass


def test_worker_contract_requires_and_canonicalizes_tenant_id():
    observed = []

    @tenant_context_worker
    def work(*, tenant_id):
        observed.append((tenant_id, get_current_tenant_id()))
        return tenant_id

    tenant_id = uuid.uuid4()
    assert work(tenant_id=str(tenant_id)) == tenant_id
    assert observed == [(tenant_id, tenant_id)]
    assert work.isolation_contract == "tenant_context"

    with pytest.raises(MissingTenantContext, match="requires tenant_id"):
        work()


def test_middleware_reads_profile_and_wraps_response_in_context():
    tenant_id = uuid.uuid4()
    request = SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=True,
            profile=SimpleNamespace(tenant_id=str(tenant_id)),
            tenant_id=str(uuid.uuid4()),
        )
    )
    seen = []

    def response_handler(received_request):
        seen.append((received_request, get_current_tenant_id()))
        return HttpResponse(status=204)

    response = TenantContextMiddleware(response_handler)(request)

    assert response.status_code == 204
    assert seen == [(request, tenant_id)]
    assert get_current_tenant_id() is None


def test_middleware_does_not_open_context_for_anonymous_request():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    response = HttpResponse(status=200)

    with patch("src.core.middleware.tenant_context.tenant_context") as context:
        assert TenantContextMiddleware(lambda unused: response)(request) is response

    context.assert_not_called()


def test_middleware_rejects_malformed_profile_tenant():
    request = SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=True,
            profile=SimpleNamespace(tenant_id="not-a-uuid"),
        )
    )

    with pytest.raises(PermissionDenied, match="invalid tenant context"):
        TenantContextMiddleware(lambda unused: HttpResponse())(request)


def test_rls_migration_is_postgresql_only_and_reversible():
    migration = importlib.import_module("src.core.migrations.0011_apply_typed_rls_to_notifications")
    postgres = SimpleNamespace(
        connection=SimpleNamespace(vendor="postgresql"),
        statements=[],
    )
    postgres.execute = postgres.statements.append
    sqlite = SimpleNamespace(
        connection=SimpleNamespace(vendor="sqlite"),
        statements=[],
    )
    sqlite.execute = sqlite.statements.append

    migration.install_typed_rls(None, postgres)
    migration.remove_typed_rls(None, postgres)
    migration.install_typed_rls(None, sqlite)
    migration.remove_typed_rls(None, sqlite)

    assert len(postgres.statements) == 2
    assert "RETURNS UUID" in postgres.statements[0]
    assert "saraise_enable_rls('notifications'::REGCLASS)" in postgres.statements[0]
    assert "DISABLE ROW LEVEL SECURITY" in postgres.statements[1]
    assert sqlite.statements == []


@pytest.mark.postgresql
@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="PostgreSQL RLS behavior requires the docker PostgreSQL database",
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["select", "insert", "update", "delete"])
def test_database_policy_blocks_cross_tenant_rows(operation):
    """Exercise RLS as a non-owner because PostgreSQL superusers bypass RLS."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    row_a = uuid.uuid4()
    row_b = uuid.uuid4()
    user_id = uuid.uuid4()
    role_name = f"saraise_rls_{uuid.uuid4().hex}"

    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{role_name}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
        cursor.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO "{role_name}"')
        cursor.executemany(
            """
            INSERT INTO notifications (
                id, tenant_id, user_id, type, title, message, read,
                action_url, metadata, created_at, updated_at
            ) VALUES (%s, %s, %s, 'info', %s, 'message', FALSE, '', '{}', NOW(), NOW())
            """,
            [
                [row_a, tenant_a, user_id, "tenant-a"],
                [row_b, tenant_b, user_id, "tenant-b"],
            ],
        )

    try:
        with tenant_context(tenant_a):
            with connection.cursor() as cursor:
                cursor.execute(f'SET LOCAL ROLE "{role_name}"')
                cursor.execute("SELECT id FROM notifications ORDER BY title")
                assert cursor.fetchall() == [(row_a,)]

                if operation == "select":
                    cursor.execute("SELECT id FROM notifications WHERE id = %s", [row_b])
                    assert cursor.fetchone() is None
                elif operation == "insert":
                    with pytest.raises(DatabaseError), transaction.atomic():
                        cursor.execute(
                            """
                            INSERT INTO notifications (
                                id, tenant_id, user_id, type, title, message, read,
                                action_url, metadata, created_at, updated_at
                            ) VALUES (%s, %s, %s, 'info', 'blocked', 'message', FALSE, '', '{}', NOW(), NOW())
                            """,
                            [uuid.uuid4(), tenant_b, user_id],
                        )
                elif operation == "update":
                    cursor.execute(
                        "UPDATE notifications SET title = 'blocked' WHERE id = %s",
                        [row_b],
                    )
                    assert cursor.rowcount == 0
                else:
                    cursor.execute("DELETE FROM notifications WHERE id = %s", [row_b])
                    assert cursor.rowcount == 0
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM notifications WHERE id IN (%s, %s)", [row_a, row_b])
            cursor.execute(f'DROP OWNED BY "{role_name}"')
            cursor.execute(f'DROP ROLE IF EXISTS "{role_name}"')
