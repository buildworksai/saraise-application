"""Tests for envelope key management backends."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.core.encryption.key_management import EnvelopeEncryptionService, KeyManagementError, SettingsKeyRingBackend


def test_settings_key_ring_encrypts_unwraps_and_rejects_unknown_keys(settings):
    first = Fernet.generate_key().decode("ascii")
    second = Fernet.generate_key().decode("ascii")
    settings.SARAISE_ENCRYPTION_KEYS = {"old": first, "active": second}
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "active"

    backend = SettingsKeyRingBackend()
    data_key = Fernet.generate_key()

    wrapped = backend.wrap_data_key("active", data_key)

    assert backend.active_key_id == "active"
    assert backend.unwrap_data_key("active", wrapped) == data_key
    with pytest.raises(KeyManagementError, match="Unknown encryption key id"):
        backend.wrap_data_key("missing", data_key)
    with pytest.raises(KeyManagementError, match="Unknown encryption key id"):
        backend.unwrap_data_key("missing", wrapped)


@pytest.mark.parametrize(
    ("keys", "active", "message"),
    [
        ({}, "", "required"),
        ({"available": Fernet.generate_key().decode("ascii")}, "missing", "not present"),
        ({"active": "not-a-fernet-key"}, "active", "invalid Fernet key"),
    ],
)
def test_settings_key_ring_fails_closed_for_missing_or_invalid_configuration(settings, keys, active, message):
    settings.SARAISE_ENCRYPTION_KEYS = keys
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = active

    with pytest.raises(KeyManagementError, match=message):
        SettingsKeyRingBackend()


def test_settings_key_ring_rejects_tampered_wrapped_data_key(settings):
    settings.SARAISE_ENCRYPTION_KEYS = {"active": Fernet.generate_key().decode("ascii")}
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "active"
    backend = SettingsKeyRingBackend()

    with pytest.raises(KeyManagementError, match="failed authentication"):
        backend.unwrap_data_key("active", "not-a-fernet-token")


def test_envelope_service_round_trips_and_rewraps_with_backend(settings):
    old = Fernet.generate_key().decode("ascii")
    active = Fernet.generate_key().decode("ascii")
    settings.SARAISE_ENCRYPTION_KEYS = {"old": old, "active": active}
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "old"
    old_service = EnvelopeEncryptionService()
    envelope = old_service.encrypt("tenant-secret")

    assert envelope.key_id == "old"
    assert old_service.decrypt(envelope.ciphertext, envelope.wrapped_data_key, envelope.key_id) == "tenant-secret"

    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "active"
    new_service = EnvelopeEncryptionService()
    rewrapped_key, new_key_id = new_service.rewrap(envelope.wrapped_data_key, envelope.key_id)

    assert new_key_id == "active"
    assert new_service.decrypt(envelope.ciphertext, rewrapped_key, new_key_id) == "tenant-secret"
    with pytest.raises(KeyManagementError, match="ciphertext failed authentication"):
        new_service.decrypt("not-a-token", rewrapped_key, new_key_id)
