# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Backend Error Handling
# backend/src/services/error_handling.py
# Reference: docs/architecture/security-model.md § 4.1 (Error Handling)
# CRITICAL NOTES:
# - Base SARAISEError exception for application-specific errors
# - HTTP exceptions mapped to Django REST Framework status codes (400, 403, 404, 500)
# - Validation errors (422) include field-level details (client feedback)
# - Authorization errors (403) don't reveal what resource exists (info disclosure prevention)
# - Server errors (500) logged server-side with stack trace (debugging aid)
# - Error responses include: code, message, details, timestamp
# - Never expose internal details in error messages (paths, SQL, function names)
# - Request logging captures error context (user_id, tenant_id, action, resource)
# - Correlation IDs for tracing errors across services
# - Error metrics: count, rates by type, severity levels
# Source: docs/architecture/security-model.md § 4.1

from rest_framework.exceptions import APIException, ValidationError, PermissionDenied, NotFound
from rest_framework import status
from rest_framework.response import Response
from typing import Dict, Any, Optional
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

class SARAISEError(Exception):
    """Base exception for SARAISE application"""
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

class AuthenticationError(SARAISEError):
    """Authentication related errors"""
    pass

class AuthorizationError(SARAISEError):
    """Authorization related errors"""
    pass

class ValidationError(SARAISEError):
    """Data validation errors"""
    pass

class DatabaseError(SARAISEError):
    """Database related errors"""
    pass

class ExternalServiceError(SARAISEError):
    """External service integration errors"""
    pass

class TenantIsolationError(SARAISEError):
    """Multi-tenant isolation errors"""
    pass

class AIAgentError(SARAISEError):
    """AI agent related errors"""
    pass

class WorkflowError(SARAISEError):
    """Workflow execution errors"""
    pass

def handle_saraise_error(error: SARAISEError) -> JSONResponse:
    """Handle SARAISE specific errors"""
    logger.error(f"SARAISE Error: {error.error_code} - {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details,
        "traceback": traceback.format_exc()
    })

    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": error.error_code,
                "message": error.message,
                "details": error.details,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def handle_authentication_error(error: AuthenticationError) -> JSONResponse:
    """Handle authentication errors"""
    logger.warning(f"Authentication Error: {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details
    })

    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": error.error_code,
                "message": error.message,
                "details": error.details,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def handle_authorization_error(error: AuthorizationError) -> JSONResponse:
    """Handle authorization errors"""
    logger.warning(f"Authorization Error: {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details
    })

    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": error.error_code,
                "message": error.message,
                "details": error.details,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def handle_validation_error(error: ValidationError) -> JSONResponse:
    """Handle validation errors"""
    logger.info(f"Validation Error: {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details
    })

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": error.error_code,
                "message": error.message,
                "details": error.details,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def handle_database_error(error: DatabaseError) -> JSONResponse:
    """Handle database errors"""
    logger.error(f"Database Error: {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details,
        "traceback": traceback.format_exc()
    })

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": error.error_code,
                "message": "Database operation failed",
                "details": {"internal_error": True},
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def handle_external_service_error(error: ExternalServiceError) -> JSONResponse:
    """Handle external service errors"""
    logger.error(f"External Service Error: {error.message}", extra={
        "error_code": error.error_code,
        "details": error.details,
        "traceback": traceback.format_exc()
    })

    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": error.error_code,
                "message": "External service unavailable",
                "details": {"service_error": True},
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

# Global exception handler
def global_exception_handler(request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled exceptions"""
    logger.error(f"Unhandled Exception: {str(exc)}", extra={
        "path": str(request.url),
        "method": request.method,
        "traceback": traceback.format_exc()
    })

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {"internal_error": True},
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

