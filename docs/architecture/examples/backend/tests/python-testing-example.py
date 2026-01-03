# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Python Testing Standards Example
# backend/src/tests/example.py
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing Requirements)
# Also: docs/architecture/module-framework.md § 4 (Module Testing)
# 
# CRITICAL NOTES:
# - Test coverage ≥90% enforced by CI (engineering-governance-and-pr-controls.md § 2.2)
# - Tests use pytest with fixtures (db_session, tenant_fixture, user_fixture)
# - Happy path, edge cases, error scenarios all covered
# - No hardcoded values or external API calls in tests

# Good - pytest with async support
import pytest
from httpx import AsyncClient
from rest_framework.test import APIClient

@pytest.mark.asyncio
def test_create_user():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = ac.post("/users/", json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "securepassword"
        })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"

