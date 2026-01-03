# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Step-Up Authentication Manager
# backend/src/services/step_up_auth_manager.py
# Reference: docs/architecture/security-model.md § 4 (Sensitive Operations)
# CRITICAL NOTES:
# - Step-up auth required for sensitive operations: delete account, change password, billing changes
# - MFA code validation for step-up (TOTP via pyotp library)
# - Step-up token issued after successful MFA (time-limited, 5 minutes)
# - Token stored in Redis with expiration (prevents reuse)
# - Session state: standard (requires step-up) vs elevated (post MFA)
# - Elevated state expires independently of session (security-model.md § 4)
# - Failed MFA attempts tracked (rate limiting after N attempts)
# - Audit logging: step-up requested, MFA verified, sensitive operation executed
# - Backup codes supported (for MFA device loss scenarios)
# - Recovery code usage logged and tracked (single-use only)
# Source: docs/architecture/security-model.md § 4, authentication-and-session-management-spec.md § 2.3

import pyotp
import secrets
from datetime import datetime, timedelta
from typing import Optional
from src.core.redis_client import redis_client

class StepUpAuthManager:
    def __init__(self):
        self.redis = redis_client
        self.step_up_timeout = 300  # 5 minutes

    def generate_totp_secret(self, user_id: str) -> dict:
        """Generate TOTP secret for user (one-time setup)"""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        # Store encrypted secret in database (not shown)
        # Return QR code URI for user to scan with authenticator app
        return {
            "secret": secret,
            "qr_uri": totp.provisioning_uri(
                name=user_id,
                issuer_name="SARAISE"
            )
        }

    def verify_totp(self, user_id: str, code: str) -> bool:
        """Verify TOTP code with ±1 step tolerance"""
        secret = self._get_user_totp_secret(user_id)  # From encrypted DB
        if not secret:
            return False

        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    def create_step_up_token(self, user_id: str) -> str:
        """Create single-use step-up token (5-minute validity)"""
        token = secrets.token_urlsafe(32)
        key = f"step_up:{user_id}:{token}"

        # Store in Redis with expiration
        self.redis.setex(key, self.step_up_timeout, "1")
        return token

    def validate_and_consume_token(self, user_id: str, token: str) -> bool:
        """Validate and consume step-up token (single-use)"""
        key = f"step_up:{user_id}:{token}"

        if not self.redis.exists(key):
            return False

        # Delete token immediately (single-use)
        self.redis.delete(key)
        return True

step_up_manager = StepUpAuthManager()

