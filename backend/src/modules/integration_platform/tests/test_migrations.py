"""PostgreSQL migration cycle and RLS policy verification."""

import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytest_plugins = ["src.core.testing"]
pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgresql]


def test_forward_reverse_forward_cycle_and_rls(settings):
    if connection.vendor != "postgresql":
        pytest.skip("UUID casts and RLS require PostgreSQL")
    assert connection.pg_version >= 170000
    settings.SARAISE_ALLOW_SECRET_ROLLBACK = True
    executor = MigrationExecutor(connection)
    executor.migrate([("integration_platform", "0002_add_integration_models")])
    old = executor.loader.project_state([("integration_platform", "0002_add_integration_models")]).apps
    connector = old.get_model("integration_platform", "Connector").objects.create(
        id=str(uuid.uuid4()), name="Legacy", connector_type="api", schema={}, config={}, is_active=True
    )
    integration = old.get_model("integration_platform", "Integration").objects.create(
        id=str(uuid.uuid4()), tenant_id=str(uuid.uuid4()), name="Legacy", integration_type="api", config={}, created_by=str(uuid.uuid4())
    )
    executor = MigrationExecutor(connection)
    executor.migrate([("integration_platform", "0005_domain_rls")])
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'integration_platform_integrations'")
        assert cursor.fetchone() == (True, True)
        cursor.execute("SELECT COUNT(*) FROM pg_policies WHERE tablename = 'integration_platform_integrations' AND qual IS NOT NULL AND with_check IS NOT NULL")
        assert cursor.fetchone()[0] == 1
    executor = MigrationExecutor(connection)
    executor.migrate([("integration_platform", "0002_add_integration_models")])
    executor = MigrationExecutor(connection)
    executor.migrate([("integration_platform", "0005_domain_rls")])
