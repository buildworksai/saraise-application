# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: CORS configuration for authentication
# backend/src/main.py
# Reference: docs/architecture/security-model.md § 3.2 (CORS and Session Security)
# CRITICAL NOTES:
# - CORS origins from environment (never hardcoded)
# - allow_credentials=True enables session cookies in cross-origin requests
# - allowed_methods: GET, POST, PUT, DELETE, PATCH (standard CRUD)
# - allowed_headers: * allows all headers OR restricted list for security
# - Preflight requests (OPTIONS) handled automatically
# - Session cookie SameSite attribute: Strict (prevent CSRF)
# - CORS misconfigurations prevent unauthorized cross-origin access
# - Invalid origins rejected by browser (CORS error blocks requests)
# - Security headers enforce origin validation (origin, referer checks)
# Source: docs/architecture/security-model.md § 3.2

from django.middleware.cors import CorsMiddleware
from src.core.security import get_cors_origins, get_security_config

security_config = get_security_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=security_config['cors']['allow_credentials'],
    allow_methods=security_config['cors']['allow_methods'],
    allow_headers=security_config['cors']['allow_headers'],
)

