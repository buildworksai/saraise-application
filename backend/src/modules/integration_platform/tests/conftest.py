"""Production-faithful security configuration for module tests."""

import pytest

from src.core.encryption.service import EncryptionService


@pytest.fixture(autouse=True)
def configured_encryption(settings, monkeypatch):
    """Exercise real Fernet encryption without weakening production fail-closed behavior."""

    monkeypatch.delenv("SARAISE_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("SARAISE_ENCRYPTION_KEY", raising=False)
    settings.SARAISE_ENCRYPTION_KEYS = None
    settings.SARAISE_ENCRYPTION_KEY = EncryptionService.rotate_key()
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None
    yield
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None
