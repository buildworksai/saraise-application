"""Tests for Secret Service.

Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.modules.ai_agent_management.egress_models import Secret, SecretAccess
from src.modules.ai_agent_management.models import Agent, AgentExecution, AgentIdentityType
from src.modules.ai_agent_management.secret_service import SecretService


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

        retrieved_value = service.get_secret(
            secret_name="api-key",
            tenant_id=tenant_id,
            accessed_by="user-1",
        )

        assert retrieved_value is not None
        assert retrieved_value == "secret-value"

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

        retrieved_value = service.get_secret(
            secret_name="api-key",
            tenant_id=tenant2,
            accessed_by="user-1",
        )

        assert retrieved_value is None  # Should not access other tenant's secret

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

        value = service.get_secret(
            secret_name="api-key",
            tenant_id=tenant_id,
            accessed_by="user-1",
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

        # SecretService doesn't have update_secret, use rotate_secret instead
        rotated = service.rotate_secret(
            secret_name="api-key",
            tenant_id=tenant_id,
            new_secret_value="new-value",
            rotated_by="user-1",
        )

        assert rotated is not None
        value = service.get_secret(secret_name="api-key", tenant_id=tenant_id, accessed_by="user-1")
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

        # SecretService doesn't have delete_secret, use deactivate_secret instead
        deactivated = service.deactivate_secret(
            secret_name="api-key",
            tenant_id=tenant_id,
        )

        assert deactivated is not None
        deactivated.refresh_from_db()
        assert deactivated.is_active is False

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
            secret_name="api-key",
            tenant_id=tenant_id,
            new_secret_value="new-value",
            rotated_by="user-1",
        )

        assert rotated is not None
        # Verify new value can be retrieved
        new_value = service.get_secret(secret_name="api-key", tenant_id=tenant_id, accessed_by="user-1")
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

        # Access is logged automatically when get_secret is called
        value = service.get_secret(
            secret_name="api-key",
            tenant_id=tenant_id,
            agent_execution=execution,
            accessed_by="user-1",
        )

        assert value == "secret-value"
        # Verify access was logged
        from src.modules.ai_agent_management.egress_models import SecretAccess

        access = SecretAccess.objects.filter(secret=secret, agent_execution=execution).first()
        assert access is not None
        assert access.secret == secret
        assert access.agent_execution == execution
