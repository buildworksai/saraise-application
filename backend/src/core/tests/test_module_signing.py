"""Tests for Module Signing.

Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import pytest

from src.core.module_manifest_schema import ModuleLifecycle, ModuleManifest, ModuleType
from src.core.module_signing import ManifestSigner, SigningError, VerificationError


class TestManifestSigner:
    """Test ManifestSigner."""

    def test_generate_rsa_keypair(self) -> None:
        """Test generating RSA keypair."""
        private_key, public_key = ManifestSigner.generate_rsa_keypair()

        assert private_key is not None
        assert public_key is not None
        assert b"BEGIN PRIVATE KEY" in private_key
        assert b"BEGIN PUBLIC KEY" in public_key

    def test_sign_rs256(self) -> None:
        """Test signing with RS256."""
        private_key, public_key = ManifestSigner.generate_rsa_keypair()

        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(private_key=private_key, public_key=public_key)
        signature, algorithm = signer.sign(manifest, algorithm="RS256")

        assert signature is not None
        assert algorithm == "RS256"

    def test_sign_rs256_no_private_key(self) -> None:
        """Test signing fails without private key."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner()
        with pytest.raises(SigningError, match="Private key required"):
            signer.sign(manifest, algorithm="RS256")

    def test_sign_hmac_sha256(self) -> None:
        """Test signing with HMAC-SHA256."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(hmac_secret="test-secret-key")
        signature, algorithm = signer.sign(manifest, algorithm="HMAC-SHA256")

        assert signature is not None
        assert algorithm == "HMAC-SHA256"

    def test_sign_hmac_sha256_no_secret(self) -> None:
        """Test signing fails without HMAC secret."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner()
        with pytest.raises(SigningError, match="HMAC secret required"):
            signer.sign(manifest, algorithm="HMAC-SHA256")

    def test_sign_unsupported_algorithm(self) -> None:
        """Test signing fails with unsupported algorithm."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner()
        with pytest.raises(SigningError, match="Unsupported algorithm"):
            signer.sign(manifest, algorithm="INVALID")

    def test_verify_rs256(self) -> None:
        """Test verifying RS256 signature."""
        private_key, public_key = ManifestSigner.generate_rsa_keypair()

        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(private_key=private_key, public_key=public_key)
        signature, algorithm = signer.sign(manifest, algorithm="RS256")

        # Verify signature
        is_valid = signer.verify(manifest, signature, algorithm)
        assert is_valid is True

    def test_verify_rs256_invalid_signature(self) -> None:
        """Test verification fails with invalid signature."""
        private_key, public_key = ManifestSigner.generate_rsa_keypair()

        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(public_key=public_key)
        invalid_signature = "invalid-signature"

        with pytest.raises(VerificationError):
            signer.verify(manifest, invalid_signature, "RS256")

    def test_verify_rs256_no_public_key(self) -> None:
        """Test verification fails without public key."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner()
        with pytest.raises(VerificationError, match="Public key required"):
            signer.verify(manifest, "signature", "RS256")

    def test_verify_hmac_sha256(self) -> None:
        """Test verifying HMAC-SHA256 signature."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(hmac_secret="test-secret-key")
        signature, algorithm = signer.sign(manifest, algorithm="HMAC-SHA256")

        # Verify signature
        is_valid = signer.verify(manifest, signature, algorithm)
        assert is_valid is True

    def test_verify_hmac_sha256_invalid_signature(self) -> None:
        """Test verification fails with invalid HMAC signature."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(hmac_secret="test-secret-key")
        invalid_signature = "invalid-signature"

        with pytest.raises(VerificationError, match="signature mismatch"):
            signer.verify(manifest, invalid_signature, "HMAC-SHA256")

    def test_verify_hmac_sha256_wrong_secret(self) -> None:
        """Test verification fails with wrong HMAC secret."""
        manifest = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer1 = ManifestSigner(hmac_secret="secret-1")
        signature, algorithm = signer1.sign(manifest, algorithm="HMAC-SHA256")

        # Try to verify with different secret
        signer2 = ManifestSigner(hmac_secret="secret-2")
        with pytest.raises(VerificationError, match="signature mismatch"):
            signer2.verify(manifest, signature, algorithm)

    def test_verify_manifest_tampering(self) -> None:
        """Test verification fails when manifest is tampered."""
        private_key, public_key = ManifestSigner.generate_rsa_keypair()

        manifest1 = ModuleManifest(
            name="test-module",
            version="1.0.0",
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        signer = ManifestSigner(private_key=private_key, public_key=public_key)
        signature, algorithm = signer.sign(manifest1, algorithm="RS256")

        # Tamper with manifest
        manifest2 = ModuleManifest(
            name="test-module",
            version="1.0.1",  # Changed version
            description="Test module",
            type=ModuleType.DOMAIN,
            lifecycle=ModuleLifecycle.MANAGED,
        )

        # Verification should fail
        with pytest.raises(VerificationError):
            signer.verify(manifest2, signature, algorithm)
