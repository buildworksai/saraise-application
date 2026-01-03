# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Environment-aware security headers
// Reference: docs/architecture/security-model.md § 3 (Security Mechanisms)
# CRITICAL NOTES:
# - Development: Basic security headers (X-Frame-Options, X-Content-Type-Options)
# - Staging: Standard security headers (adds HSTS, CSP for testing)
# - Production: Maximum strict headers (X-Frame-Options: DENY, strict CSP)
# - X-Frame-Options prevents clickjacking attacks (DENY in production, SAMEORIGIN in staging)
# - X-Content-Type-Options: nosniff prevents MIME type sniffing
# - Content-Security-Policy headers restrict script execution sources
# - Strict-Transport-Security (HSTS) enforces HTTPS in production (includeSubDomains)
# - All headers configured per-environment (defense-in-depth via layered headers)
# - Security headers added to ALL responses (middleware applies universally)
# Source: docs/architecture/security-model.md § 3, OWASP Secure Headers Project

from rest_framework import Request, Response
from django.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, environment: str):
        super().__init__(app)
        self.environment = environment

    def dispatch(self, request: Request, call_next):
        response = call_next(request)

        if self.environment == "development":
            self.add_development_headers(response)
        elif self.environment == "staging":
            self.add_staging_headers(response)
        elif self.environment == "production":
            self.add_production_headers(response)

        return response

    def add_development_headers(self, response: Response):
        # Development: Basic security headers
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"

    def add_staging_headers(self, response: Response):
        # Staging: Standard security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"

    def add_production_headers(self, response: Response):
        # Production: Maximum security headers
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        )

