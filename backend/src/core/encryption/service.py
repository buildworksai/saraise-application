"""
Encryption Service Implementation.

Uses Fernet (symmetric encryption) for secure secret storage.
Fernet guarantees that a message encrypted using it cannot be manipulated or read without the key.

SPDX-License-Identifier: Apache-2.0
"""

import base64
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data."""

    _fernet: Optional[Fernet] = None

    @classmethod
    def _get_encryption_key(cls) -> bytes:
        """Get or generate encryption key from environment variable.

        Returns:
            Encryption key as bytes.

        Raises:
            ValueError: If key cannot be generated or retrieved.
        """
        # Try to get key from environment
        key_str = getattr(settings, "SARAISE_ENCRYPTION_KEY", None) or os.getenv("SARAISE_ENCRYPTION_KEY")

        if key_str:
            # Key provided - use it directly (must be base64-encoded 32-byte key)
            try:
                return base64.urlsafe_b64decode(key_str.encode())
            except Exception as e:
                logger.error(f"Failed to decode encryption key: {e}")
                raise ValueError("Invalid encryption key format. Must be base64-encoded 32-byte key.")

        # No key provided - generate from password (for development only)
        # In production, MUST set SARAISE_ENCRYPTION_KEY environment variable
        password = getattr(settings, "SARAISE_ENCRYPTION_PASSWORD", "saraise-dev-key-change-in-production")
        salt = getattr(settings, "SARAISE_ENCRYPTION_SALT", b"saraise-salt-change-in-production")

        logger.warning(
            "Using password-based key derivation. "
            "Set SARAISE_ENCRYPTION_KEY environment variable for production."
        )

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Get or create Fernet instance.

        Returns:
            Fernet instance for encryption/decryption.
        """
        if cls._fernet is None:
            key = cls._get_encryption_key()
            cls._fernet = Fernet(key)
        return cls._fernet

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Encrypt plaintext string.

        Args:
            plaintext: String to encrypt.

        Returns:
            Base64-encoded encrypted string.

        Raises:
            ValueError: If encryption fails.
        """
        try:
            fernet = cls._get_fernet()
            encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
            return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise ValueError(f"Failed to encrypt data: {e}")

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Decrypt ciphertext string.

        Args:
            ciphertext: Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.

        Raises:
            ValueError: If decryption fails (invalid token, wrong key, etc.).
        """
        try:
            fernet = cls._get_fernet()
            encrypted_bytes = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key or corrupted data)")
            raise ValueError("Failed to decrypt data: Invalid token. Key may be incorrect or data corrupted.")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Failed to decrypt data: {e}")

    @classmethod
    def rotate_key(cls, old_key: Optional[str] = None) -> str:
        """Generate a new encryption key.

        Args:
            old_key: Optional old key for re-encryption (not implemented yet).

        Returns:
            New base64-encoded encryption key.

        Note:
            Key rotation requires re-encrypting all existing secrets.
            This method only generates a new key - re-encryption must be done separately.
        """
        new_key = Fernet.generate_key()
        return base64.urlsafe_b64encode(new_key).decode("utf-8")

    @classmethod
    def re_encrypt(cls, old_ciphertext: str, old_key: str, new_key: str) -> str:
        """Re-encrypt data with a new key.

        Args:
            old_ciphertext: Data encrypted with old key.
            old_key: Old encryption key (base64-encoded).
            new_key: New encryption key (base64-encoded).

        Returns:
            Data encrypted with new key.

        Raises:
            ValueError: If re-encryption fails.
        """
        try:
            # Decrypt with old key
            old_fernet = Fernet(base64.urlsafe_b64decode(old_key.encode()))
            encrypted_bytes = base64.urlsafe_b64decode(old_ciphertext.encode("utf-8"))
            plaintext = old_fernet.decrypt(encrypted_bytes).decode("utf-8")

            # Encrypt with new key
            new_fernet = Fernet(base64.urlsafe_b64decode(new_key.encode()))
            encrypted_bytes = new_fernet.encrypt(plaintext.encode("utf-8"))
            return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Re-encryption failed: {e}")
            raise ValueError(f"Failed to re-encrypt data: {e}")
