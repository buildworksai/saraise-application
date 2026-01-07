"""Module Manifest Signing & Verification.

Implements manifest signing and verification for module security.
Task: 501.1 - Module Manifest Schema & Signing
"""

from __future__ import annotations

import hashlib
import hmac
import base64
from typing import Optional, Tuple
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
)
from cryptography.hazmat.backends import default_backend

from .module_manifest_schema import ModuleManifest


class SigningError(Exception):
    """Signing error."""

    pass


class VerificationError(Exception):
    """Verification error."""

    pass


class ManifestSigner:
    """Manifest signer.

    Signs and verifies module manifests.
    """

    SUPPORTED_ALGORITHMS = ["RS256", "HMAC-SHA256"]

    def __init__(
        self,
        private_key: Optional[bytes] = None,
        public_key: Optional[bytes] = None,
        hmac_secret: Optional[str] = None,
    ) -> None:
        """Initialize signer.

        Args:
            private_key: RSA private key (PEM format) for RS256.
            public_key: RSA public key (PEM format) for RS256.
            hmac_secret: HMAC secret for HMAC-SHA256.
        """
        self.private_key = private_key
        self.public_key = public_key
        self.hmac_secret = hmac_secret

    def sign(
        self, manifest: ModuleManifest, algorithm: str = "RS256"
    ) -> Tuple[str, str]:
        """Sign a manifest.

        Args:
            manifest: ModuleManifest instance.
            algorithm: Signing algorithm (RS256 or HMAC-SHA256).

        Returns:
            Tuple of (signature, algorithm).

        Raises:
            SigningError: If signing fails.
        """
        content_hash = manifest.get_content_hash()

        if algorithm == "RS256":
            if not self.private_key:
                raise SigningError("Private key required for RS256 signing")

            try:
                key = load_pem_private_key(
                    self.private_key, password=None, backend=default_backend()
                )
                signature_bytes = key.sign(
                    content_hash.encode(),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA256(),
                )
                signature = base64.b64encode(signature_bytes).decode()
                return signature, algorithm

            except Exception as e:
                raise SigningError(f"RS256 signing failed: {e}") from e

        elif algorithm == "HMAC-SHA256":
            if not self.hmac_secret:
                raise SigningError("HMAC secret required for HMAC-SHA256 signing")

            try:
                signature_bytes = hmac.new(
                    self.hmac_secret.encode(), content_hash.encode(), hashlib.sha256
                ).digest()
                signature = base64.b64encode(signature_bytes).decode()
                return signature, algorithm

            except Exception as e:
                raise SigningError(f"HMAC-SHA256 signing failed: {e}") from e

        else:
            raise SigningError(f"Unsupported algorithm: {algorithm}")

    def verify(
        self, manifest: ModuleManifest, signature: str, algorithm: str
    ) -> bool:
        """Verify a manifest signature.

        Args:
            manifest: ModuleManifest instance.
            signature: Signature to verify.
            algorithm: Signing algorithm.

        Returns:
            True if signature is valid.

        Raises:
            VerificationError: If verification fails.
        """
        content_hash = manifest.get_content_hash()

        if algorithm == "RS256":
            if not self.public_key:
                raise VerificationError("Public key required for RS256 verification")

            try:
                key = load_pem_public_key(
                    self.public_key, backend=default_backend()
                )
                signature_bytes = base64.b64decode(signature)
                key.verify(
                    signature_bytes,
                    content_hash.encode(),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH,
                    ),
                    hashes.SHA256(),
                )
                return True

            except Exception as e:
                raise VerificationError(f"RS256 verification failed: {e}") from e

        elif algorithm == "HMAC-SHA256":
            if not self.hmac_secret:
                raise VerificationError(
                    "HMAC secret required for HMAC-SHA256 verification"
                )

            try:
                expected_signature_bytes = hmac.new(
                    self.hmac_secret.encode(), content_hash.encode(), hashlib.sha256
                ).digest()
                expected_signature = base64.b64encode(expected_signature_bytes).decode()

                # Constant-time comparison
                if hmac.compare_digest(signature, expected_signature):
                    return True
                else:
                    raise VerificationError("HMAC signature mismatch")

            except Exception as e:
                raise VerificationError(f"HMAC-SHA256 verification failed: {e}") from e

        else:
            raise VerificationError(f"Unsupported algorithm: {algorithm}")

    @staticmethod
    def generate_rsa_keypair() -> Tuple[bytes, bytes]:
        """Generate RSA keypair for signing.

        Returns:
            Tuple of (private_key, public_key) in PEM format.
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        public_key = private_key.public_key()

        private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )
        public_pem = public_key.public_bytes(
            encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
        )

        return private_pem, public_pem


# Global signer instance (should be configured with keys)
manifest_signer = ManifestSigner()
