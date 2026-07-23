"""Migration graph completeness proof; PostgreSQL RLS behavior runs in its dedicated gate."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db
def test_purchase_migration_graph_reaches_domain_registration():
    leaves = set(MigrationExecutor(connection).loader.graph.leaf_nodes("purchase_management"))
    assert ("purchase_management", "0008_domain_contract_registration") in leaves
