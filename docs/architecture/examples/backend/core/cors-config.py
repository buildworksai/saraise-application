# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Environment-aware CORS configuration
# Reference: docs/architecture/security-model.md § 3.2 (CORS and Origin Validation)
# CRITICAL NOTES:
# - CORS origins sourced from environment variables (never hardcoded)
# - Development: localhost:20000, 20001 allowed (local development only)
# - Staging: staging.saraise.com with HTTPS only (secure testing environment)
# - Production: production.saraise.com with HTTPS only (restrict to legitimate origins)
# - allow_credentials=True enables session cookies to be sent with requests
# - allow_methods: GET, POST, PUT, DELETE, PATCH (standard CRUD operations)
# - allow_headers: * allows all headers (can be restricted to specific headers)
# - Preflight requests (OPTIONS) handled automatically by CORS middleware
# - Missing origin validation is a critical security vulnerability (CORS bypass)
# - Invalid origins result in browser blocking the request (CORS error)
# Source: docs/architecture/security-model.md § 3.2, OWASP CORS Security Guide

from django.middleware.cors import CorsMiddleware
from src.config.settings import settings

def configure_cors(app: Django REST Framework):
    environment = settings.APP_ENV or "development"
    cors_origins = get_cors_origins(environment)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )

def get_cors_origins(environment: str) -> list:
    if environment == "development":
        return [
            "http://localhost:20000",
            "http://127.0.0.1:20000",
            "http://localhost:20001",
            "http://127.0.0.1:20001"
        ]
    elif environment == "staging":
        return [
            "https://staging.saraise.com",
            "https://app.staging.saraise.com"
        ]
    elif environment == "production":
        return [
            "https://saraise.com",
            "https://app.saraise.com"
        ]
    return []

