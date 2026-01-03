# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Customization Testing with Tenant Isolation
# backend/src/customization/tests/test_customization.py
# Reference: docs/architecture/security-model.md (Row-Level Multitenancy)

import pytest
from src.customization.services.custom_field_customizer import CustomFieldCustomizer

def test_add_custom_field(db_session, tenant_fixture):
    """Test adding custom field with explicit tenant_id."""
    tenant = tenant_fixture(name="test-tenant-1")
    customizer = CustomFieldCustomizer(db_session, tenant_id=tenant.id)

    custom_field = customizer.add_custom_field_to_entity(
        entity_name="customer",
        fieldname="custom_phone",
        label="Phone Number",
        fieldtype="String"
    )

    assert custom_field.fieldname == "custom_phone"
    assert custom_field.tenant_id == tenant.id
    assert custom_field.entity_name == "customer"

def test_customization_isolation(db_session, tenant_fixture):
    """Test tenant isolation for customizations via explicit tenant_id filtering."""
    tenant1 = tenant_fixture(name="tenant-1")
    tenant2 = tenant_fixture(name="tenant-2")
    
    customizer1 = CustomFieldCustomizer(db_session, tenant_id=tenant1.id)
    customizer2 = CustomFieldCustomizer(db_session, tenant_id=tenant2.id)

    # Add custom field for tenant 1
    field1 = customizer1.add_custom_field_to_entity(
        entity_name="customer",
        fieldname="custom_phone",
        label="Phone Number",
        fieldtype="String"
    )
    
    # Add custom field for tenant 2 with same name but different definition
    field2 = customizer2.add_custom_field_to_entity(
        entity_name="customer",
        fieldname="custom_phone",
        label="Mobile Phone",
        fieldtype="Integer"
    )

    assert field1.tenant_id == tenant1.id
    assert field2.tenant_id == tenant2.id
    assert field1.id != field2.id
    # Both can have same fieldname because they're isolated by tenant_id

    # Get custom fields for tenant 2
    fields2 = customizer.get_custom_fields("User", test_tenant2.id)

    # Tenant 2 should not see tenant 1's custom field
    assert field1.fieldname not in [f.fieldname for f in fields2]

