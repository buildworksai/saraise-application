# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: CORS Configuration for Session Cookies
# Reference: docs/architecture/security-model.md § 3.2 (CORS Enforcement)
# Also: docs/architecture/authentication-and-session-management-spec.md § 3 (Session Security)
# 
# CRITICAL NOTES:
# - CORS origins MUST be explicitly listed (never wildcard *) to prevent XSS via CORS
# - HTTP-only cookies require credentials: true in CORS config
# - SameSite attribute enforced (Strict for maximum security)

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

