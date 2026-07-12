"""Pluggable key management for envelope encryption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils.module_loading import import_string


class KeyManagementError(RuntimeError):
    """Raised when key management is unavailable or misconfigured."""


class KeyManagementBackend(Protocol):
    """Contract implemented by local key rings and external KMS adapters."""

    @property
    def active_key_id(self) -> str: ...

    def wrap_data_key(self, key_id: str, data_key: bytes) -> str: ...

    def unwrap_data_key(self, key_id: str, wrapped_data_key: str) -> bytes: ...


class SettingsKeyRingBackend:
    """Master-key backend configured by ``SARAISE_ENCRYPTION_KEYS``.

    The mapping is ``key_id -> Fernet key``. Operators rotate by adding a new
    key, changing ``SARAISE_ACTIVE_ENCRYPTION_KEY_ID``, rewrapping records, and
    only then removing the retired key. No key is generated implicitly.
    """

    def __init__(self) -> None:
        keys: Mapping[str, str] = getattr(settings, "SARAISE_ENCRYPTION_KEYS", {})
        self._active_key_id = getattr(settings, "SARAISE_ACTIVE_ENCRYPTION_KEY_ID", "")
        if not keys or not self._active_key_id:
            raise KeyManagementError("SARAISE_ENCRYPTION_KEYS and SARAISE_ACTIVE_ENCRYPTION_KEY_ID are required")
        if self._active_key_id not in keys:
            raise KeyManagementError("Active encryption key id is not present in SARAISE_ENCRYPTION_KEYS")
        try:
            self._keys = {key_id: Fernet(value.encode("ascii")) for key_id, value in keys.items()}
        except (TypeError, ValueError) as exc:
            raise KeyManagementError("SARAISE_ENCRYPTION_KEYS contains an invalid Fernet key") from exc

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def wrap_data_key(self, key_id: str, data_key: bytes) -> str:
        try:
            return self._keys[key_id].encrypt(data_key).decode("ascii")
        except KeyError as exc:
            raise KeyManagementError(f"Unknown encryption key id: {key_id}") from exc

    def unwrap_data_key(self, key_id: str, wrapped_data_key: str) -> bytes:
        try:
            return self._keys[key_id].decrypt(wrapped_data_key.encode("ascii"))
        except KeyError as exc:
            raise KeyManagementError(f"Unknown encryption key id: {key_id}") from exc
        except InvalidToken as exc:
            raise KeyManagementError("Wrapped data key failed authentication") from exc


@dataclass(frozen=True)
class Envelope:
    """Serialized envelope-encryption result."""

    ciphertext: str
    wrapped_data_key: str
    key_id: str


class EnvelopeEncryptionService:
    """Encrypt each value with a unique data key protected by a master key."""

    def __init__(self, backend: KeyManagementBackend | None = None) -> None:
        if backend is None:
            backend_path = getattr(
                settings,
                "SARAISE_KEY_MANAGEMENT_BACKEND",
                "src.core.encryption.key_management.SettingsKeyRingBackend",
            )
            backend = import_string(backend_path)()
        self.backend = backend

    def encrypt(self, plaintext: str) -> Envelope:
        data_key = Fernet.generate_key()
        key_id = self.backend.active_key_id
        return Envelope(
            ciphertext=Fernet(data_key).encrypt(plaintext.encode("utf-8")).decode("ascii"),
            wrapped_data_key=self.backend.wrap_data_key(key_id, data_key),
            key_id=key_id,
        )

    def decrypt(self, ciphertext: str, wrapped_data_key: str, key_id: str) -> str:
        data_key = self.backend.unwrap_data_key(key_id, wrapped_data_key)
        try:
            return Fernet(data_key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise KeyManagementError("Secret ciphertext failed authentication") from exc

    def rewrap(self, wrapped_data_key: str, old_key_id: str) -> tuple[str, str]:
        data_key = self.backend.unwrap_data_key(old_key_id, wrapped_data_key)
        new_key_id = self.backend.active_key_id
        return self.backend.wrap_data_key(new_key_id, data_key), new_key_id
