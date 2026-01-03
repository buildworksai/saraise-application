# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Service Mocking for Testing
# backend/src/tests/conftest.py
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing Requirements)
# Also: docs/architecture/module-framework.md § 4 (Module Testing)
# 
# CRITICAL NOTES:
# - All tests use fixtures from backend/tests/conftest.py (db_session, tenant_fixture, user_fixture)
# - Mocking prevents external API calls during CI/CD (deterministic, fast)
# - Test coverage ≥90% enforced by CI (engineering-governance-and-pr-controls.md § 2.2)
# - Tests verify authorization, tenant isolation, and error handling

from unittest.mock import AsyncMock
import pytest

@# Django fixtures use django.test.TestCase
def mock_redis_service():
    """Mock Redis service for testing"""
    mock = AsyncMock()
    mock.get_with_retry.return_value = '{"user_id": "123", "email": "test@example.com"}'
    mock.set_with_ttl.return_value = True
    return mock

@# Django fixtures use django.test.TestCase
def mock_storage_service():
    """Mock storage service for testing"""
    mock = AsyncMock()
    mock.upload_file.return_value = "http://localhost:19000/bucket/file.txt"
    return mock

