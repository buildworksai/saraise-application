"""
Tests for Encryption Service.

SPDX-License-Identifier: Apache-2.0
"""

import base64
import pytest
from cryptography.fernet import Fernet

from ..service import EncryptionService


class TestEncryptionService:
    """Test encryption and decryption functionality."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test: Encrypt and decrypt returns original value."""
        plaintext = "my-secret-api-key-12345"
        ciphertext = EncryptionService.encrypt(plaintext)
        decrypted = EncryptionService.decrypt(ciphertext)

        assert decrypted == plaintext
        assert ciphertext != plaintext  # Encrypted should be different

    def test_encrypt_produces_different_output(self):
        """Test: Same plaintext produces different ciphertext (non-deterministic)."""
        plaintext = "test-secret"
        ciphertext1 = EncryptionService.encrypt(plaintext)
        ciphertext2 = EncryptionService.encrypt(plaintext)

        # Should be different due to random IV
        assert ciphertext1 != ciphertext2

        # But both should decrypt to same value
        assert EncryptionService.decrypt(ciphertext1) == plaintext
        assert EncryptionService.decrypt(ciphertext2) == plaintext

    def test_decrypt_invalid_token_raises_error(self):
        """Test: Decrypting invalid token raises ValueError."""
        invalid_ciphertext = "invalid-encrypted-data"

        with pytest.raises(ValueError, match="Failed to decrypt"):
            EncryptionService.decrypt(invalid_ciphertext)

    def test_decrypt_wrong_key_raises_error(self):
        """Test: Decrypting with wrong key raises ValueError."""
        plaintext = "secret-data"
        ciphertext = EncryptionService.encrypt(plaintext)

        # Create different Fernet instance (different key)
        different_key = Fernet.generate_key()
        different_fernet = Fernet(different_key)

        # Try to decrypt with wrong key
        encrypted_bytes = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        with pytest.raises(ValueError, match="Invalid token"):
            different_fernet.decrypt(encrypted_bytes)

    def test_encrypt_empty_string(self):
        """Test: Encrypt and decrypt empty string."""
        plaintext = ""
        ciphertext = EncryptionService.encrypt(plaintext)
        decrypted = EncryptionService.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_encrypt_unicode_string(self):
        """Test: Encrypt and decrypt Unicode string."""
        plaintext = "🔐 Secret: 秘密のキー 🗝️"
        ciphertext = EncryptionService.encrypt(plaintext)
        decrypted = EncryptionService.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_encrypt_long_string(self):
        """Test: Encrypt and decrypt long string."""
        plaintext = "x" * 10000  # 10KB string
        ciphertext = EncryptionService.encrypt(plaintext)
        decrypted = EncryptionService.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_rotate_key_generates_new_key(self):
        """Test: Key rotation generates new key."""
        key1 = EncryptionService.rotate_key()
        key2 = EncryptionService.rotate_key()

        assert key1 != key2
        assert len(key1) > 0
        assert len(key2) > 0

    def test_re_encrypt_with_different_keys(self):
        """Test: Re-encrypt data with different keys."""
        plaintext = "original-secret"
        old_key = EncryptionService.rotate_key()
        new_key = EncryptionService.rotate_key()

        # Encrypt with old key manually
        old_fernet = Fernet(base64.urlsafe_b64decode(old_key.encode()))
        old_ciphertext = base64.urlsafe_b64encode(old_fernet.encrypt(plaintext.encode())).decode()

        # Re-encrypt with new key
        new_ciphertext = EncryptionService.re_encrypt(old_ciphertext, old_key, new_key)

        # Decrypt with new key
        new_fernet = Fernet(base64.urlsafe_b64decode(new_key.encode()))
        encrypted_bytes = base64.urlsafe_b64decode(new_ciphertext.encode("utf-8"))
        decrypted = new_fernet.decrypt(encrypted_bytes).decode("utf-8")

        assert decrypted == plaintext
