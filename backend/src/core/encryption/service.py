"""Fail-closed encryption for secrets stored by SARAISE.

Keys are supplied by the deployment environment (directly, or through a secret
manager that populates Django settings).  The service deliberately has no
development fallback: every mode exercises the same Fernet code path.

SPDX-License-Identifier: Apache-2.0
"""

import base64
import binascii
import logging
import os
from collections.abc import Sequence
from typing import ClassVar, cast

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class EncryptionConfigurationError(ImproperlyConfigured):
    """Raised when encryption keys are missing or malformed."""


class EncryptionService:
    """Encrypt and decrypt text with an ordered Fernet key ring.

    ``SARAISE_ENCRYPTION_KEYS`` is a comma-separated key ring whose first key
    is the primary encryption key.  Remaining keys are decrypt-only rotation
    keys.  ``SARAISE_ENCRYPTION_KEY`` remains supported as the single-key
    configuration for existing deployments.

    Environment variables take precedence over same-named Django settings.
    This lets a secret manager inject settings while preserving a simple,
    twelve-factor deployment path.  Values must be standard URL-safe,
    base64-encoded 32-byte Fernet keys, such as ``Fernet.generate_key()``.
    """

    KEY_RING_SETTING: ClassVar[str] = "SARAISE_ENCRYPTION_KEYS"
    SINGLE_KEY_SETTING: ClassVar[str] = "SARAISE_ENCRYPTION_KEY"

    _fernet: ClassVar[MultiFernet | None] = None
    _cached_keys: ClassVar[tuple[bytes, ...] | None] = None

    @classmethod
    def _read_configuration(cls) -> str | Sequence[str] | None:
        """Read the configured key material without applying mode-specific logic."""
        for name in (cls.KEY_RING_SETTING, cls.SINGLE_KEY_SETTING):
            environment_value = os.getenv(name)
            if environment_value and environment_value.strip():
                return environment_value

        for name in (cls.KEY_RING_SETTING, cls.SINGLE_KEY_SETTING):
            setting_value = getattr(settings, name, None)
            if setting_value is not None:
                return cast(str | Sequence[str], setting_value)

        return None

    @classmethod
    def _get_encryption_keys(cls) -> tuple[bytes, ...]:
        """Return validated Fernet keys in primary-first order.

        Raises:
            EncryptionConfigurationError: If no key is configured or any key
                is not a standard Fernet key.
        """
        configured = cls._read_configuration()
        if configured is None:
            raise EncryptionConfigurationError(
                "Encryption is unavailable: set SARAISE_ENCRYPTION_KEYS (primary first) or SARAISE_ENCRYPTION_KEY."
            )

        if isinstance(configured, str):
            key_values = configured.split(",")
        elif isinstance(configured, Sequence):
            key_values = list(configured)
        else:
            raise EncryptionConfigurationError(
                "Encryption key configuration must be a Fernet key or an ordered key sequence."
            )

        normalized: list[bytes] = []
        for position, value in enumerate(key_values, start=1):
            if not isinstance(value, str) or not value.strip():
                raise EncryptionConfigurationError(f"Encryption key {position} is empty or is not text.")

            try:
                key = value.strip().encode("ascii")
                Fernet(key)
            except (TypeError, UnicodeError, ValueError) as exc:
                raise EncryptionConfigurationError(f"Encryption key {position} is not a valid Fernet key.") from exc
            normalized.append(key)

        if not normalized:
            raise EncryptionConfigurationError("At least one encryption key is required.")

        return tuple(normalized)

    @classmethod
    def _get_encryption_key(cls) -> bytes:
        """Return the primary key for compatibility with existing callers."""
        return cls._get_encryption_keys()[0]

    @classmethod
    def _get_fernet(cls) -> MultiFernet:
        """Return a key-ring cipher, refreshing it when configuration changes."""
        keys = cls._get_encryption_keys()
        if cls._fernet is None or cls._cached_keys != keys:
            cls._fernet = MultiFernet([Fernet(key) for key in keys])
            cls._cached_keys = keys
        return cls._fernet

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Encrypt text using the primary key and return a standard Fernet token."""
        fernet = cls._get_fernet()
        try:
            return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
        except (AttributeError, UnicodeError, ValueError) as exc:
            logger.error("Encryption failed", exc_info=True)
            raise ValueError("Failed to encrypt data.") from exc

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """Decrypt a standard or legacy-wrapped token with the configured keys.

        Releases before the fail-closed refactor wrapped Fernet's already-base64
        token in one extra base64 layer.  Reading that envelope remains
        supported so configured deployments can migrate stored credentials;
        all new encryption returns standard Fernet tokens.
        """
        fernet = cls._get_fernet()
        try:
            token = ciphertext.encode("ascii")
            try:
                decrypted = fernet.decrypt(token)
            except InvalidToken:
                legacy_token = base64.b64decode(token, altchars=b"-_", validate=True)
                decrypted = fernet.decrypt(legacy_token)
            return decrypted.decode("utf-8")
        except (binascii.Error, InvalidToken, UnicodeError, ValueError, AttributeError) as exc:
            logger.error("Decryption failed: invalid token or plaintext encoding")
            raise ValueError(
                "Failed to decrypt data: token is invalid, corrupted, or encrypted with an unavailable key."
            ) from exc

    @classmethod
    def rotate_key(cls, old_key: str | None = None) -> str:
        """Generate a standard Fernet key suitable as the next primary key.

        ``old_key`` is retained only for source compatibility.  Rotation is
        activated by configuring the returned key before the previous keys in
        ``SARAISE_ENCRYPTION_KEYS``.
        """
        del old_key
        return Fernet.generate_key().decode("ascii")

    @classmethod
    def re_encrypt(cls, old_ciphertext: str, old_key: str, new_key: str) -> str:
        """Rotate one token from ``old_key`` to ``new_key``.

        MultiFernet performs the decrypt/re-encrypt operation and preserves the
        token timestamp.  Both arguments use the same standard Fernet key
        format as the environment configuration.
        """
        try:
            old_fernet = Fernet(old_key.strip().encode("ascii"))
            new_fernet = Fernet(new_key.strip().encode("ascii"))
            token = old_ciphertext.encode("ascii")
            key_ring = MultiFernet([new_fernet, old_fernet])
            try:
                rotated = key_ring.rotate(token)
            except InvalidToken:
                legacy_token = base64.b64decode(token, altchars=b"-_", validate=True)
                rotated = key_ring.rotate(legacy_token)
            return rotated.decode("ascii")
        except (binascii.Error, InvalidToken, TypeError, ValueError, UnicodeError, AttributeError) as exc:
            logger.error("Re-encryption failed: invalid token or key")
            raise ValueError("Failed to re-encrypt data: invalid token or Fernet key.") from exc
