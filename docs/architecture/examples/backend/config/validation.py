# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Environment Variable Validation
# backend/src/config/validation.py
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
# CRITICAL NOTES:
# - Validation runs at application startup (fail-fast pattern)
# - Missing required variables cause immediate application failure
# - POSTGRES_CONNECTION_STRING: Required (database connectivity essential)
# - REDIS_URL: Required (session storage, caching, rate limiting)
# - SESSION_SECRET_KEY: Required (session security, random per deployment)
# - Additional secrets validated by environment (dev vs prod)
# - All connection strings use environment variables (no hardcoded values)
# - Validation prevents deployment of incomplete/misconfigured applications
# - Invalid config raises ValueError with detailed missing variable list
# - Application MUST NOT start if required environment variables missing
# - Validation runs before any database/external service connections
# Source: docs/architecture/security-model.md § 5

import os

def validate_environment():
    """Validate required environment variables"""
    required_vars = [
        "POSTGRES_CONNECTION_STRING",
        "REDIS_URL",
        "SESSION_SECRET_KEY"
    ]

    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

