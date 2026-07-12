"""Secret Isolation Service.

Implements secret isolation and management for AI agents.
Task: 402.1 - Egress Allowlisting & Secret Isolation
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from django.utils import timezone

from src.core.encryption.key_management import EnvelopeEncryptionService

from .egress_models import Secret, SecretAccess
from .models import AgentExecution

logger = logging.getLogger(__name__)


class SecretService:
    """Service for managing secrets with per-tenant isolation."""

    def __init__(self, encryption: Optional[EnvelopeEncryptionService] = None) -> None:
        """Initialize secret service."""
        self._encryption = encryption

    @property
    def encryption(self) -> EnvelopeEncryptionService:
        """Resolve key management lazily so imports never mask configuration failures."""
        if self._encryption is None:
            self._encryption = EnvelopeEncryptionService()
        return self._encryption

    def create_secret(
        self,
        tenant_id: str,
        name: str,
        secret_value: str,
        secret_type: str,
        description: str = "",
        expires_at: Optional[datetime] = None,
        rotation_interval_days: Optional[int] = None,
        created_by: str = "",
    ) -> Secret:
        """Create a secret.

        Args:
            tenant_id: Tenant ID.
            name: Secret name.
            secret_value: Secret value (will be encrypted).
            secret_type: Secret type (api_key, password, token, etc.).
            description: Secret description.
            expires_at: Optional expiration time.
            rotation_interval_days: Optional rotation interval.
            created_by: User who created the secret.

        Returns:
            Created Secret instance.

        Raises:
            ValueError: If validation fails or secret already exists.
        """
        # Check if secret already exists
        existing = Secret.objects.filter(tenant_id=tenant_id, name=name, is_active=True).first()

        if existing:
            raise ValueError(f"Secret {name} already exists for tenant {tenant_id}")

        # Encrypt secret value
        envelope = self.encryption.encrypt(secret_value)

        # Create secret
        secret = Secret.objects.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            secret_type=secret_type,
            encrypted_value=envelope.ciphertext,
            encryption_key_id=envelope.key_id,
            wrapped_data_key=envelope.wrapped_data_key,
            expires_at=expires_at,
            rotation_interval_days=rotation_interval_days,
            created_by=created_by,
        )

        logger.info(f"Created secret {secret.id} for tenant {tenant_id}")

        return secret

    def get_secret(
        self,
        secret_name: str,
        tenant_id: str,
        agent_execution: Optional[AgentExecution] = None,
        accessed_by: str = "",
    ) -> Optional[str]:
        """Get secret value (decrypted).

        Args:
            secret_name: Secret name.
            tenant_id: Tenant ID.
            agent_execution: Optional agent execution instance.
            accessed_by: User/agent accessing the secret.

        Returns:
            Decrypted secret value or None if not found.

        Raises:
            ValueError: If secret not found or expired.
        """
        secret = Secret.objects.filter(tenant_id=tenant_id, name=secret_name, is_active=True).first()

        if not secret:
            return None

        # Check expiration
        if secret.expires_at and timezone.now() > secret.expires_at:
            logger.warning(f"Secret {secret_name} has expired")
            raise ValueError(f"Secret {secret_name} has expired")

        # Decrypt secret
        if not secret.wrapped_data_key:
            raise ValueError("Legacy secret requires explicit re-encryption before it can be read")
        secret_value = self.encryption.decrypt(
            secret.encrypted_value, secret.wrapped_data_key, secret.encryption_key_id
        )

        # Log access
        SecretAccess.objects.create(
            tenant_id=tenant_id,
            secret=secret,
            agent_execution=agent_execution,
            accessed_by=accessed_by,
            metadata={"secret_name": secret_name},
        )

        logger.info(f"Accessed secret {secret_name} by {accessed_by}")

        return secret_value

    def rotate_secret(
        self,
        secret_name: str,
        tenant_id: str,
        new_secret_value: str,
        rotated_by: str = "",
    ) -> Secret:
        """Rotate a secret.

        Args:
            secret_name: Secret name.
            tenant_id: Tenant ID.
            new_secret_value: New secret value.
            rotated_by: User who rotated the secret.

        Returns:
            Updated Secret instance.

        Raises:
            ValueError: If secret not found.
        """
        secret = Secret.objects.filter(tenant_id=tenant_id, name=secret_name, is_active=True).first()

        if not secret:
            raise ValueError(f"Secret {secret_name} not found")
        # Encrypt new value
        envelope = self.encryption.encrypt(new_secret_value)

        # Update secret
        secret.encrypted_value = envelope.ciphertext
        secret.wrapped_data_key = envelope.wrapped_data_key
        secret.encryption_key_id = envelope.key_id
        secret.last_rotated_at = timezone.now()

        # Update expiration if rotation interval is set
        if secret.rotation_interval_days:
            secret.expires_at = timezone.now() + timedelta(days=secret.rotation_interval_days)

        secret.save(
            update_fields=[
                "encrypted_value",
                "wrapped_data_key",
                "encryption_key_id",
                "last_rotated_at",
                "expires_at",
                "updated_at",
            ]
        )

        logger.info(f"Rotated secret {secret_name} for tenant {tenant_id}")

        return secret

    def list_secrets(
        self,
        tenant_id: str,
        secret_type: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Secret]:
        """List secrets for tenant.

        Args:
            tenant_id: Tenant ID.
            secret_type: Optional secret type filter.
            is_active: Optional active filter.

        Returns:
            List of Secret instances (without decrypted values).
        """
        query = Secret.objects.filter(tenant_id=tenant_id)

        if secret_type:
            query = query.filter(secret_type=secret_type)

        if is_active is not None:
            query = query.filter(is_active=is_active)

        return list(query.order_by("name"))

    def deactivate_secret(self, secret_name: str, tenant_id: str) -> Secret:
        """Deactivate a secret.

        Args:
            secret_name: Secret name.
            tenant_id: Tenant ID.

        Returns:
            Updated Secret instance.

        Raises:
            ValueError: If secret not found.
        """
        secret = Secret.objects.filter(tenant_id=tenant_id, name=secret_name, is_active=True).first()

        if not secret:
            raise ValueError(f"Secret {secret_name} not found")

        secret.is_active = False
        secret.save(update_fields=["is_active", "updated_at"])

        logger.info(f"Deactivated secret {secret_name} for tenant {tenant_id}")

        return secret

    def check_expired_secrets(self, tenant_id: str) -> List[Secret]:
        """Check for expired secrets.

        Args:
            tenant_id: Tenant ID.

        Returns:
            List of expired Secret instances.
        """
        expired = Secret.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
            expires_at__lte=timezone.now(),
        )

        return list(expired)

    def rotate_master_key(self, secret_name: str, tenant_id: str) -> Secret:
        """Rewrap a secret's data key under the active master key without exposing plaintext."""
        secret = Secret.objects.filter(tenant_id=tenant_id, name=secret_name, is_active=True).first()
        if not secret:
            raise ValueError(f"Secret {secret_name} not found")
        if not secret.wrapped_data_key:
            raise ValueError("Legacy secret cannot be rewrapped; rotate its value explicitly")
        wrapped_data_key, key_id = self.encryption.rewrap(secret.wrapped_data_key, secret.encryption_key_id)
        secret.wrapped_data_key = wrapped_data_key
        secret.encryption_key_id = key_id
        secret.last_rotated_at = timezone.now()
        secret.save(update_fields=["wrapped_data_key", "encryption_key_id", "last_rotated_at", "updated_at"])
        return secret


# Global secret service instance
secret_service = SecretService()
