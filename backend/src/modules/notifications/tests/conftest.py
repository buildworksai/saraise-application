"""Production-shaped notification test fixtures."""

import pytest
from cryptography.fernet import Fernet

pytest_plugins = ["src.core.testing"]


@pytest.fixture(autouse=True)
def notification_encryption(settings, monkeypatch):
    monkeypatch.delenv("SARAISE_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("SARAISE_ENCRYPTION_KEY", raising=False)
    settings.SARAISE_ENCRYPTION_KEYS = None
    settings.SARAISE_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.SARAISE_ENVIRONMENT = "development"
