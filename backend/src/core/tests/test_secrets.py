"""Security contract tests for the fail-closed encryption foundation.

SPDX-License-Identifier: Apache-2.0
"""

import base64
import inspect

import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.core.encryption import EncryptionConfigurationError, EncryptionService


@pytest.fixture(autouse=True)
def reset_encryption_service(monkeypatch):
    """Keep configuration and the process-local cipher cache isolated per test."""
    monkeypatch.delenv(EncryptionService.KEY_RING_SETTING, raising=False)
    monkeypatch.delenv(EncryptionService.SINGLE_KEY_SETTING, raising=False)
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None
    yield
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None


@pytest.mark.parametrize("mode", ["development", "self-hosted", "saas"])
def test_missing_key_fails_closed_in_every_mode(mode, monkeypatch, settings):
    """No operating mode may synthesize or bypass missing key material."""
    settings.SARAISE_MODE = mode
    settings.SARAISE_ENCRYPTION_KEYS = None
    settings.SARAISE_ENCRYPTION_KEY = None
    settings.SARAISE_ENCRYPTION_PASSWORD = "legacy-password"
    settings.SARAISE_ENCRYPTION_SALT = b"legacy-salt"

    with pytest.raises(EncryptionConfigurationError, match="Encryption is unavailable"):
        EncryptionService.encrypt("must-not-be-encrypted")


def test_environment_key_round_trip_uses_standard_fernet_token(monkeypatch):
    """The configured key and produced token interoperate with Fernet directly."""
    key = Fernet.generate_key()
    monkeypatch.setenv(EncryptionService.SINGLE_KEY_SETTING, key.decode("ascii"))

    ciphertext = EncryptionService.encrypt("my-secret-api-key")

    assert ciphertext != "my-secret-api-key"
    assert EncryptionService.decrypt(ciphertext) == "my-secret-api-key"
    assert Fernet(key).decrypt(ciphertext.encode("ascii")) == b"my-secret-api-key"
    assert EncryptionService._get_encryption_key() == key


def test_rotation_decrypts_old_tokens_and_encrypts_with_primary(monkeypatch):
    """A primary-first key ring decrypts old data but never encrypts with old keys."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ciphertext = Fernet(old_key).encrypt(b"survives-rotation").decode("ascii")
    monkeypatch.setenv(
        EncryptionService.KEY_RING_SETTING,
        f" {new_key.decode('ascii')} , {old_key.decode('ascii')} ",
    )

    assert EncryptionService.decrypt(old_ciphertext) == "survives-rotation"

    new_ciphertext = EncryptionService.encrypt("uses-primary")
    assert Fernet(new_key).decrypt(new_ciphertext.encode("ascii")) == b"uses-primary"
    with pytest.raises(InvalidToken):
        Fernet(old_key).decrypt(new_ciphertext.encode("ascii"))


def test_key_ring_change_refreshes_cached_cipher(monkeypatch):
    """A secret-manager refresh takes effect without retaining stale encryption state."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    monkeypatch.setenv(EncryptionService.SINGLE_KEY_SETTING, old_key.decode("ascii"))
    old_cipher = EncryptionService.encrypt("old")

    monkeypatch.delenv(EncryptionService.SINGLE_KEY_SETTING)
    monkeypatch.setenv(
        EncryptionService.KEY_RING_SETTING,
        f"{new_key.decode('ascii')},{old_key.decode('ascii')}",
    )
    new_cipher = EncryptionService.encrypt("new")

    assert EncryptionService.decrypt(old_cipher) == "old"
    assert Fernet(new_key).decrypt(new_cipher.encode("ascii")) == b"new"


def test_secret_manager_can_supply_an_ordered_settings_key_ring(settings):
    """Secret-manager integrations may expose an ordered sequence via settings."""
    primary = Fernet.generate_key().decode("ascii")
    secondary = Fernet.generate_key().decode("ascii")
    settings.SARAISE_ENCRYPTION_KEYS = [primary, secondary]
    settings.SARAISE_ENCRYPTION_KEY = None

    ciphertext = EncryptionService.encrypt("settings-backed")

    assert Fernet(primary.encode("ascii")).decrypt(ciphertext.encode("ascii")) == b"settings-backed"


def test_environment_configuration_takes_precedence_over_secret_manager_settings(monkeypatch, settings):
    environment_key = Fernet.generate_key()
    settings.SARAISE_ENCRYPTION_KEYS = [Fernet.generate_key().decode("ascii")]
    monkeypatch.setenv(EncryptionService.SINGLE_KEY_SETTING, environment_key.decode("ascii"))

    ciphertext = EncryptionService.encrypt("environment-wins")

    assert Fernet(environment_key).decrypt(ciphertext.encode("ascii")) == b"environment-wins"


@pytest.mark.parametrize(
    "configured",
    [
        "not-a-fernet-key",
        "valid-looking-but-not-valid=",
        "key-one,,key-three",
        "clé-non-ascii",
        [Fernet.generate_key().decode("ascii"), ""],
    ],
)
def test_malformed_key_ring_fails_closed(configured, monkeypatch, settings):
    if isinstance(configured, str):
        monkeypatch.setenv(EncryptionService.KEY_RING_SETTING, configured)
    else:
        settings.SARAISE_ENCRYPTION_KEYS = configured
        settings.SARAISE_ENCRYPTION_KEY = None

    with pytest.raises(EncryptionConfigurationError, match="Encryption key"):
        EncryptionService.encrypt("secret")


def test_non_text_settings_configuration_fails_closed(settings):
    settings.SARAISE_ENCRYPTION_KEYS = object()
    settings.SARAISE_ENCRYPTION_KEY = None

    with pytest.raises(EncryptionConfigurationError, match="must be a Fernet key"):
        EncryptionService.encrypt("secret")


def test_empty_settings_key_ring_fails_closed(settings):
    settings.SARAISE_ENCRYPTION_KEYS = []
    settings.SARAISE_ENCRYPTION_KEY = None

    with pytest.raises(EncryptionConfigurationError, match="At least one"):
        EncryptionService.encrypt("secret")


def test_invalid_ciphertext_and_non_text_inputs_are_explicit_failures(monkeypatch):
    monkeypatch.setenv(
        EncryptionService.SINGLE_KEY_SETTING,
        Fernet.generate_key().decode("ascii"),
    )

    with pytest.raises(ValueError, match="Failed to decrypt data"):
        EncryptionService.decrypt("not-a-fernet-token")
    with pytest.raises(ValueError, match="Failed to encrypt data"):
        EncryptionService.encrypt(None)  # type: ignore[arg-type]


def test_decrypted_plaintext_must_be_utf8(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv(EncryptionService.SINGLE_KEY_SETTING, key.decode("ascii"))
    ciphertext = Fernet(key).encrypt(b"\xff").decode("ascii")

    with pytest.raises(ValueError, match="Failed to decrypt data"):
        EncryptionService.decrypt(ciphertext)


def test_decrypt_supports_exactly_one_legacy_ciphertext_envelope(monkeypatch):
    """Stored tokens from the old double-encoding implementation remain readable."""
    key = Fernet.generate_key()
    monkeypatch.setenv(EncryptionService.SINGLE_KEY_SETTING, key.decode("ascii"))
    standard_token = Fernet(key).encrypt(b"legacy-stored-secret")
    legacy_ciphertext = base64.urlsafe_b64encode(standard_token).decode("ascii")

    assert EncryptionService.decrypt(legacy_ciphertext) == "legacy-stored-secret"

    twice_wrapped = base64.urlsafe_b64encode(legacy_ciphertext.encode("ascii")).decode("ascii")
    with pytest.raises(ValueError, match="Failed to decrypt data"):
        EncryptionService.decrypt(twice_wrapped)


def test_rotate_key_and_re_encrypt_use_standard_fernet_formats():
    old_key = EncryptionService.rotate_key("ignored-for-source-compatibility")
    new_key = EncryptionService.rotate_key()
    old_ciphertext = Fernet(old_key.encode("ascii")).encrypt(b"rotate-me").decode("ascii")

    new_ciphertext = EncryptionService.re_encrypt(old_ciphertext, old_key, new_key)

    assert Fernet(new_key.encode("ascii")).decrypt(new_ciphertext.encode("ascii")) == b"rotate-me"
    with pytest.raises(InvalidToken):
        Fernet(old_key.encode("ascii")).decrypt(new_ciphertext.encode("ascii"))


def test_re_encrypt_migrates_legacy_ciphertext_envelope():
    old_key = EncryptionService.rotate_key()
    new_key = EncryptionService.rotate_key()
    old_token = Fernet(old_key.encode("ascii")).encrypt(b"legacy-rotate")
    legacy_ciphertext = base64.urlsafe_b64encode(old_token).decode("ascii")

    new_ciphertext = EncryptionService.re_encrypt(legacy_ciphertext, old_key, new_key)

    assert Fernet(new_key.encode("ascii")).decrypt(new_ciphertext.encode("ascii")) == b"legacy-rotate"


@pytest.mark.parametrize(
    ("ciphertext", "old_key", "new_key"),
    [
        ("invalid-token", Fernet.generate_key().decode("ascii"), Fernet.generate_key().decode("ascii")),
        ("invalid-token", "invalid-key", Fernet.generate_key().decode("ascii")),
    ],
)
def test_re_encrypt_rejects_invalid_tokens_and_keys(ciphertext, old_key, new_key):
    with pytest.raises(ValueError, match="Failed to re-encrypt data"):
        EncryptionService.re_encrypt(ciphertext, old_key, new_key)


def test_no_hardcoded_or_password_derived_fallback_exists():
    """Guard against reintroducing the council-blocking deterministic fallback."""
    source = inspect.getsource(inspect.getmodule(EncryptionService))

    assert "PBKDF2" not in source
    assert "SARAISE_ENCRYPTION_PASSWORD" not in source
    assert "SARAISE_ENCRYPTION_SALT" not in source
    assert "saraise-dev-key" not in source
    assert "saraise-salt" not in source


def test_public_and_legacy_import_paths_remain_available():
    """Representative callers can import both supported service paths."""
    from src.core.encryption import EncryptionService as PublicService
    from src.core.encryption.service import EncryptionService as LegacyService
    from src.modules.integration_platform.services import EncryptionService as CallerService

    assert PublicService is EncryptionService
    assert LegacyService is EncryptionService
    assert CallerService is EncryptionService
