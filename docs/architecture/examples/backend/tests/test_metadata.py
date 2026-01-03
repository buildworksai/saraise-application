# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Metadata Testing with Custom Fields
# backend/tests/customization/test_metadata.py
# Reference: docs/architecture/module-framework.md § 5.2 (Custom Fields)

import pytest
from django.db import transaction
from django.test import TestCase
from src.modules.customization.services import CustomFieldService
from src.modules.customization.services import FormGenerator
from src.modules.customization.models import TenantCustomFieldDefinition

@pytest.mark.django_db
def test_add_custom_field(
    db,
    tenant_fixture
):
    """Test adding custom field via TenantCustomFieldDefinition.
    
    Custom fields use explicit tenant_id filtering per Row-Level Multitenancy.
    See docs/architecture/application-architecture.md § 2.1 for tenant isolation.
    Django tests are synchronous (per Django testing standards).
    """
    service = CustomFieldService(tenant_id=tenant_fixture.id)

    custom_field = service.add_custom_field(
        entity_name="User",
        fieldname="custom_phone",
        label="Phone Number",
        fieldtype="Data"
    )

    assert custom_field.fieldname == "custom_phone"
    assert custom_field.entity_name == "User"
    assert custom_field.tenant_id == tenant_fixture.id

@pytest.mark.django_db
def test_generate_form_schema(
    db,
    tenant_fixture
):
    """Test form schema generation for tenant.
    
    Forms include both base entity fields and tenant custom fields.
    Django tests are synchronous (no async/await).
    """
    generator = FormGenerator(tenant_id=tenant_fixture.id)
    schema = generator.generate_form_schema("User")

    assert schema["entity_name"] == "User"
    assert schema["tenant_id"] == tenant_fixture.id
    assert len(schema["fields"]) > 0
    # Custom fields should be from this tenant only
    for custom_field in schema.get("custom_fields", []):
        assert custom_field["tenant_id"] == tenant_fixture.id

