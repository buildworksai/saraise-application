"""
Encryption Service for SARAISE.

Provides secure encryption/decryption for sensitive data like API keys and secrets.
Uses Fernet (symmetric encryption) from the cryptography library.

SPDX-License-Identifier: Apache-2.0
"""

from .service import EncryptionConfigurationError, EncryptionService

__all__ = ["EncryptionConfigurationError", "EncryptionService"]
