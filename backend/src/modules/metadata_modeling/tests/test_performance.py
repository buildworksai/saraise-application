"""Query-count boundaries for indexed tenant lists."""

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from src.modules.metadata_modeling.models import EntityDefinition
from src.modules.metadata_modeling.services import EntityDefinitionService

pytest_plugins = ["src.core.testing.factories"]


@pytest.mark.django_db
def test_tenant_definition_list_is_one_bounded_query_without_cross_tenant_rows():
    tenant_id, other_tenant = uuid.uuid4(), uuid.uuid4()
    for index in range(12):
        EntityDefinition.objects.create(
            tenant_id=tenant_id,
            name=f"Asset {index:02}",
            plural_name=f"Assets {index:02}",
            code=f"asset-{index:02}",
        )
    EntityDefinition.objects.create(
        tenant_id=other_tenant,
        name="Foreign",
        plural_name="Foreign records",
        code="foreign",
    )
    with CaptureQueriesContext(connection) as queries:
        rows = list(
            EntityDefinitionService.list_definitions(tenant_id, status="draft", search="Asset", ordering="name")
        )
    assert len(rows) == 12
    assert {row.tenant_id for row in rows} == {tenant_id}
    assert len(queries) <= 2
    sql = " ".join(item["sql"] for item in queries.captured_queries).lower()
    assert "tenant_id" in sql
