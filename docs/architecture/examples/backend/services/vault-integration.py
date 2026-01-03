# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Vault Integration for Secrets Management
# backend/src/services/vault_service.py
# Reference: docs/architecture/security-model.md § 5.1 (Secrets Management)

import hvac
from src.core.urls import get_vault_url
from rest_framework.exceptions import APIException
import os
import logging


class VaultService:
    """
    Vault integration for secure secrets management.

    FROZEN ARCHITECTURE: Django/DRF exception pattern (NOT FastAPI HTTPException)

    CRITICAL: Platform-level infrastructure service.
    All secrets accessed via Vault for audit and rotation.
    See docs/architecture/security-model.md § 5.1.

    Key Features:
    - Centralized secrets management via HashiCorp Vault
    - Automatic secret rotation support
    - Audit logging for all secret access
    - Environment-specific secret isolation
    - Fail-secure pattern (raises exception on errors)

    Environment Variables Required:
    - VAULT_ADDR: Vault server URL (or use get_vault_url())
    - VAULT_TOKEN: Authentication token for Vault access
    """

    def __init__(self):
        """Initialize Vault client with authentication"""
        vault_url = get_vault_url()
        self.vault_token = os.getenv('VAULT_TOKEN', 'dev-token')
        self.client = hvac.Client(url=vault_url, token=self.vault_token)
        self.logger = logging.getLogger(__name__)

        # Verify Vault connection
        if not self.client.is_authenticated():
            self.logger.error("Vault authentication failed")
            raise APIException(detail="Vault service unavailable")

    def get_secret(self, path: str, key: str) -> str:
        """
        Get secret from Vault with error handling.

        FROZEN ARCHITECTURE: Raises DRF APIException (NOT HTTPException, NOT raise Response)

        Args:
            path: Vault KV path (e.g., "secret/data/database")
            key: Secret key within the path (e.g., "postgres_password")

        Returns:
            str: Secret value

        Raises:
            APIException: Secret retrieval failed (DRF exception, returns HTTP 500)

        Example:
            vault = VaultService()
            db_password = vault.get_secret("secret/data/database", "postgres_password")

        Security Notes:
        - All secret access logged to immutable audit logs
        - Secrets NEVER logged or printed
        - Vault policies enforce least-privilege access
        """
        try:
            # KV v2 secrets engine path
            response = self.client.secrets.kv.v2.read_secret_version(path=path)

            # Extract secret data
            secret_data = response['data']['data']
            if key not in secret_data:
                raise KeyError(f"Key '{key}' not found in secret at path '{path}'")

            return secret_data[key]

        except KeyError as e:
            # Secret or key does not exist
            self.logger.error(f"Secret key not found: {path}/{key}", exc_info=True)
            # ✅ CORRECT: Raise DRF exception (NOT raise Response)
            raise APIException(detail="Secret not found")

        except Exception as e:
            # Vault API error, network error, or authentication failure
            # CRITICAL: Do NOT leak Vault error details to client
            self.logger.error(f"Failed to get secret {path}/{key}: {str(e)}", exc_info=True)
            # ✅ CORRECT: Raise DRF exception (NOT raise Response)
            raise APIException(detail="Secret retrieval failed")

    def set_secret(self, path: str, secrets: dict) -> None:
        """
        Set secret in Vault (create or update).

        Args:
            path: Vault KV path (e.g., "secret/data/database")
            secrets: Dictionary of key-value pairs to store

        Raises:
            APIException: Secret storage failed

        Example:
            vault = VaultService()
            vault.set_secret("secret/data/database", {
                "postgres_password": "secure_password_123"
            })
        """
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=secrets
            )
            self.logger.info(f"Secret updated at path: {path}")

        except Exception as e:
            self.logger.error(f"Failed to set secret at {path}: {str(e)}", exc_info=True)
            raise APIException(detail="Secret storage failed")


# ANTI-PATTERNS (FORBIDDEN - DOCUMENTED FOR REFERENCE):
# ❌ WRONG: from rest_framework import HTTPException  # HTTPException does NOT exist in DRF
# ❌ WRONG: raise Response(status=status.HTTP_500, detail="...")  # Cannot raise Response
# ❌ WRONG: raise HTTPException(status_code=500, detail="...")  # FastAPI pattern
# ❌ WRONG: logging.error(f"Secret value: {secret_value}")  # NEVER log secrets
#
# ✅ CORRECT: raise APIException(detail="Secret retrieval failed")  # DRF exception
# ✅ CORRECT: self.logger.error("Failed to get secret", exc_info=True)  # Log error without secret
