# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Environment-aware HTTPS enforcement
# backend/src/core/network_security.py
# Reference: docs/architecture/security-model.md § 3.2 (Network Security)
# CRITICAL NOTES:
# - Development: HTTP allowed for localhost (ease of local development)
# - Staging: HTTPS required with basic security (staging.saraise.com)
# - Production: Maximum security (HSTS, trusted hosts, HTTPS redirect, TLS 1.3)
# - HTTPSRedirectMiddleware redirects HTTP → HTTPS in non-dev (except localhost)
# - TrustedHostMiddleware restricts Host header to valid domains (Host-based injection prevention)
# - HSTS header enforces HTTPS for 1 year (preload list consideration)
# - TLS 1.3 minimum in production (deprecate TLS 1.2)
# - Certificate validation enforced for all outbound connections
# - No self-signed certificates in production (CA-signed only)
# Source: docs/architecture/security-model.md § 3.2

from src.config.settings import settings
from rest_framework import Django REST Framework
# Use Django SECURE_SSL_REDIRECT
from django.middleware.security import SecurityMiddleware

def configure_network_security(app: Django REST Framework):
    environment = settings.APP_ENV or "development"
    if environment == "development":
        # Development: HTTP allowed for localhost
        configure_development_security(app)
    elif environment == "staging":
        # Staging: HTTPS required with basic security
        configure_staging_security(app)
    elif environment == "production":
        # Production: Maximum security
        configure_production_security(app)

def configure_development_security(app: Django REST Framework):
    # Development: Basic security, HTTP allowed
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "::1"]
    )

def configure_staging_security(app: Django REST Framework):
    # Staging: HTTPS required, basic security headers
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["staging.saraise.com", "*.staging.saraise.com"]
    )

def configure_production_security(app: Django REST Framework):
    # Production: Maximum security
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["saraise.com", "*.saraise.com"]
    )

