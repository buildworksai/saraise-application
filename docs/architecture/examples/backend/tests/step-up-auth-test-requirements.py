# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Step-Up Authentication Test Requirements
# Reference: docs/architecture/authentication-and-session-management-spec.md § 5 (Step-Up Auth)
# Also: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing)
# 
# CRITICAL NOTES:
# - Tests verify elevation required for sensitive operations
# - Tests verify elevation time-limited (15-30 min configurable)
# - Tests verify MFA required for elevation (SMS, TOTP, biometric)
# - Tests verify expired elevation requires re-authentication

# Test step-up authentication
def test_sensitive_operation_requires_mfa(client, admin_user):
    response = client.delete(f"/tenants/{tenant_id}")
    assert response.status_code == 428

def test_sensitive_operation_with_valid_mfa(client, admin_user):
    totp = pyotp.TOTP(admin_user.totp_secret)
    code = totp.now()

    response = client.delete(
        f"/tenants/{tenant_id}",
        headers={"X-MFA-Code": code}
    )
    assert response.status_code == 200

def test_mfa_code_reuse_blocked(client, admin_user):
    totp = pyotp.TOTP(admin_user.totp_secret)
    code = totp.now()

    # First use succeeds
    response1 = client.delete(f"/tenants/{tenant_id}", headers={"X-MFA-Code": code})
    assert response1.status_code == 200

    # Second use fails (single-use)
    response2 = client.delete(f"/tenants/{tenant_id2}", headers={"X-MFA-Code": code})
    assert response2.status_code == 403

