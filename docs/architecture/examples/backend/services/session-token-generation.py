# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Secure Session Token Generation
# Reference: docs/architecture/authentication-and-session-management-spec.md § 2 (Session Lifecycle)
# Also: docs/architecture/security-model.md § 3.2 (Session Security)
# 
# CRITICAL NOTES:
# - Session tokens MUST be cryptographically random (secrets.token_urlsafe)
# - Tokens stored in Redis backend (no server-side state leakage)
# - Tokens transmitted ONLY via HTTP-only cookies (never JavaScript accessible)

import secrets

def generate_session_token() -> str:
    # 32 bytes = 256 bits of entropy
    return secrets.token_urlsafe(32)

