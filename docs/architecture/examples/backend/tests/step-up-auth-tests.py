# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Step-Up Authentication Tests
# Reference: docs/architecture/authentication-and-session-management-spec.md § 5 (Step-Up Auth)
# Also: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing)
# 
# CRITICAL NOTES:
# - Step-up auth required for sensitive operations (password change, settings)
# - Elevation time-limited (15-30 min, configurable per operation)
# - MFA required for step-up (SMS, TOTP, biometric)
# - Expired elevation requires re-authentication

class TestStepUpAuthentication:
    def test_delete_tenant_requires_mfa(self, platform_owner_client):
        response = platform_owner_client.delete("/api/v1/tenants/tenant-1")
        assert response.status_code == 428
        assert "MFA" in response.json()["detail"]

    def test_delete_tenant_with_valid_mfa(self, platform_owner_client, platform_owner_user):
        import pyotp
        totp = pyotp.TOTP(platform_owner_user.totp_secret)
        code = totp.now()

        response = platform_owner_client.delete(
            "/api/v1/tenants/tenant-1",
            headers={"X-MFA-Code": code}
        )
        assert response.status_code == 200

    def test_mfa_code_single_use(self, platform_owner_client, platform_owner_user):
        import pyotp
        totp = pyotp.TOTP(platform_owner_user.totp_secret)
        code = totp.now()

        # First use succeeds
        response1 = platform_owner_client.delete(
            "/api/v1/tenants/tenant-1",
            headers={"X-MFA-Code": code}
        )
        assert response1.status_code == 200

        # Second use fails
        response2 = platform_owner_client.delete(
            "/api/v1/tenants/tenant-2",
            headers={"X-MFA-Code": code}
        )
        assert response2.status_code == 403

