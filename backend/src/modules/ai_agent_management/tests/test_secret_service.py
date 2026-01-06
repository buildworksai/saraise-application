"""Tests for Secret Service.

Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from datetime import timedelta

from ..models import Agent, AgentExecution, AgentIdentityType
from ..secret_service import SecretService
from ..secret_models import Secret, SecretAccess


@pytest.mark.django_db
class TestSecretService:
    """Test SecretService."""

    def test_create_secret(self) -> None:
        """Test creating a secret."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="secret-value-123",
            secret_type="api_key",
            description="API key for external service",
            created_by="user-1",
        )

        assert secret is not None
        assert secret.tenant_id == tenant_id
        assert secret.name == "api-key"
        assert secret.secret_type == "api_key"
        # Secret value should be encrypted
        assert secret.encrypted_value != "secret-value-123"

    def test_get_secret(self) -> None:
        """Test getting a secret."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        created = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="secret-value",
            secret_type="api_key",
            created_by="user-1",
        )

        retrieved = service.get_secret(
            tenant_id=tenant_id,
            secret_id=created.id,
        )

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "api-key"

    def test_get_secret_wrong_tenant(self) -> None:
        """Test getting secret from wrong tenant returns None."""
        service = SecretService()

        tenant1 = "tenant-1"
        tenant2 = "tenant-2"

        secret = service.create_secret(
            tenant_id=tenant1,
            name="api-key",
            secret_value="secret-value",
            secret_type="api_key",
            created_by="user-1",
        )

        retrieved = service.get_secret(
            tenant_id=tenant2,
            secret_id=secret.id,
        )

        assert retrieved is None  # Should not access other tenant's secret

    def test_list_secrets(self) -> None:
        """Test listing secrets."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        service.create_secret(
            tenant_id=tenant_id,
            name="api-key-1",
            secret_value="value-1",
            secret_type="api_key",
            created_by="user-1",
        )

        service.create_secret(
            tenant_id=tenant_id,
            name="api-key-2",
            secret_value="value-2",
            secret_type="api_key",
            created_by="user-1",
        )

        secrets = service.list_secrets(tenant_id=tenant_id)

        assert len(secrets) >= 2
        assert all(s.tenant_id == tenant_id for s in secrets)

    def test_get_secret_value(self) -> None:
        """Test getting decrypted secret value."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="original-value",
            secret_type="api_key",
            created_by="user-1",
        )

        value = service.get_secret_value(
            tenant_id=tenant_id,
            secret_id=secret.id,
        )

        assert value == "original-value"

    def test_update_secret(self) -> None:
        """Test updating a secret."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="old-value",
            secret_type="api_key",
            created_by="user-1",
        )

        updated = service.update_secret(
            tenant_id=tenant_id,
            secret_id=secret.id,
            secret_value="new-value",
            updated_by="user-1",
        )

        assert updated is not None
        value = service.get_secret_value(tenant_id=tenant_id, secret_id=secret.id)
        assert value == "new-value"

    def test_delete_secret(self) -> None:
        """Test deleting a secret."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="secret-value",
            secret_type="api_key",
            created_by="user-1",
        )

        service.delete_secret(
            tenant_id=tenant_id,
            secret_id=secret.id,
            deleted_by="user-1",
        )

        secret.refresh_from_db()
        assert secret.is_deleted is True

    def test_rotate_secret(self) -> None:
        """Test rotating a secret."""
        service = SecretService()

        tenant_id = "test-tenant-1"

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="old-value",
            secret_type="api_key",
            rotation_interval_days=30,
            created_by="user-1",
        )

        rotated = service.rotate_secret(
            tenant_id=tenant_id,
            secret_id=secret.id,
            new_secret_value="new-value",
            rotated_by="user-1",
        )

        assert rotated is not None
        assert rotated.version > secret.version

        # Old version should be archived
        old_value = service.get_secret_value(
            tenant_id=tenant_id, secret_id=secret.id, version=secret.version
        )
        assert old_value == "old-value"

        # New version should be current
        new_value = service.get_secret_value(tenant_id=tenant_id, secret_id=rotated.id)
        assert new_value == "new-value"

    def test_log_secret_access(self) -> None:
        """Test logging secret access."""
        service = SecretService()

        tenant_id = "test-tenant-1"
        agent = Agent.objects.create(
            tenant_id=tenant_id,
            name="Test Agent",
            description="Test agent",
            identity_type=AgentIdentityType.USER_BOUND,
            subject_id="user-1",
            session_id="session-1",
            framework="langgraph",
            config={},
            created_by="user-1",
        )

        execution = AgentExecution.objects.create(
            tenant_id=tenant_id,
            agent=agent,
            state="running",
            task_definition={"goal": "test"},
        )

        secret = service.create_secret(
            tenant_id=tenant_id,
            name="api-key",
            secret_value="secret-value",
            secret_type="api_key",
            created_by="user-1",
        )

        access = service.log_secret_access(
            tenant_id=tenant_id,
            secret_id=secret.id,
            agent_execution=execution,
            accessed_by="user-1",
        )

        assert access is not None
        assert access.secret_id == secret.id
        assert access.agent_execution_id == execution.id

