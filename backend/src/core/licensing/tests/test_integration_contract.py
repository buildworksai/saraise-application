"""
Integration contract tests: Platform generates key, Application verifies.

Phase 7.5: Licensing Subsystem
Verifies contract compatibility between saraise-platform license-server
and saraise-application licensing service.

Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import base64
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.utils import timezone

from src.core.licensing.client import LicenseClient
from src.core.licensing.models import LicenseTier
from src.core.licensing.services import LicenseService

# Enable database access for tests that need it
pytestmark = pytest.mark.django_db


def _generate_signature_platform_format(payload: dict, private_key_pem: bytes) -> str:
    """
    Sign payload using platform's exact format (PSS padding, SHA256).

    Matches license-server CryptoService.sign_license().
    """
    payload_clean = {k: v for k, v in payload.items() if k != "signature"}
    payload_bytes = json.dumps(payload_clean, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _format_license_key_platform_format(payload: dict, signature: str) -> str:
    """
    Format license key as platform does.

    Matches license-server KeyGeneratorService.format_license_key().
    """
    key_data = {**payload, "signature": signature}
    json_str = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


class TestPlatformApplicationKeyContract:
    """
    Integration contract: Platform generates key, Application decodes and verifies.

    Platform format: base64(JSON{...payload, "signature": "base64_sig"})
    Platform signing: RSA-PSS with SHA256, MAX_LENGTH salt
    """

    def test_platform_format_decode_application_verifies(self):
        """Platform generates key in format; Application decodes and verifies signature."""
        # Generate key pair (platform has private, application has public)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Build payload in platform KeyGeneratorService format
        now = timezone.now()
        expires_at = now + timedelta(days=365)
        payload = {
            "version": "1.0",
            "type": "subscription",
            "organization": {"id": "org_contract_test", "name": "Contract Test Org"},
            "license": {
                "id": "lic_123",
                "tier": "professional",
                "billing_cycle": "annual",
            },
            "core": {
                "tier": "free",
                "limits": {"max_companies": 1, "max_users": -1},
            },
            "modules": {"included": ["foundation.*", "core.*"]},
            "validity": {
                "issued_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "grace_period_days": 30,
            },
        }

        # Sign (platform logic)
        signature = _generate_signature_platform_format(payload, private_key_pem)
        license_key = _format_license_key_platform_format(payload, signature)

        # Decode (application logic)
        decoded_data, decoded_sig = LicenseService._decode_license_key(license_key)
        assert decoded_data["organization"]["id"] == "org_contract_test"
        assert decoded_data["validity"]["expires_at"] == expires_at.isoformat()
        assert decoded_sig == signature

        # Verify (application logic) with public key
        with patch("django.conf.settings.SARAISE_LICENSE_PUBLIC_KEY", public_key_pem.decode()):
            with patch("django.conf.settings.SARAISE_MODE", "self-hosted"):
                is_valid = LicenseService._verify_signature(decoded_data, decoded_sig)
                assert is_valid is True

    def test_platform_format_license_client_offline_validates(self):
        """LicenseClient._validate_offline accepts platform-generated key."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        now = timezone.now()
        expires_at = now + timedelta(days=365)
        payload = {
            "version": "1.0",
            "type": "subscription",
            "organization": {"id": "org_client_test", "name": "Client Test"},
            "license": {"id": "lic_456", "tier": "professional", "billing_cycle": "annual"},
            "core": {"tier": "free", "limits": {"max_companies": 1, "max_users": -1}},
            "modules": {"included": ["foundation.*", "core.*"]},
            "validity": {
                "issued_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "grace_period_days": 30,
            },
        }

        signature = _generate_signature_platform_format(payload, private_key_pem)
        license_key = _format_license_key_platform_format(payload, signature)

        with patch("django.conf.settings.SARAISE_LICENSE_PUBLIC_KEY", public_key_pem.decode()):
            client = LicenseClient()

            info = client._validate_offline(
                license_key=license_key,
                organization_id="org_client_test",
            )

            assert info is not None
            assert info.organization_id == "org_client_test"
            assert info.tier == LicenseTier.PROFESSIONAL
            assert len(info.licensed_modules) >= 1
            module_ids = [m.module_id for m in info.licensed_modules]
            assert "foundation.*" in module_ids or any("foundation" in m for m in module_ids)
