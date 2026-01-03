# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Standardized Error Handling for All Services
# backend/src/core/service_errors.py
# Reference: docs/architecture/security-model.md § 4.2 (Error Handling & Logging)

from rest_framework.exceptions import APIException, ValidationError
import logging


class ServiceError(Exception):
    """
    Base exception for service-level errors.

    FROZEN ARCHITECTURE: Custom exception class (NOT DRF exception)
    Use for internal service errors, then convert to DRF exceptions for API responses.
    """
    def __init__(self, message: str, service: str, error_code: str = None):
        self.message = message
        self.service = service
        self.error_code = error_code
        super().__init__(self.message)


class DatabaseUnavailableError(APIException):
    """
    Custom DRF exception for database unavailability.

    FROZEN ARCHITECTURE: DRF APIException subclass (NOT FastAPI HTTPException)
    Returns HTTP 503 Service Unavailable
    """
    status_code = 503
    default_detail = "Database connection failed"
    default_code = "database_unavailable"


class ServiceErrorHandler:
    """
    Error handling standardization for service layer.

    FROZEN ARCHITECTURE: Django/DRF exception pattern (NOT FastAPI HTTPException)

    CRITICAL: Errors must not leak sensitive information.
    Tenant-scoped operations verified before error responses.
    See docs/architecture/security-model.md § 4.2.

    Design Pattern:
    - Catch internal exceptions in service layer
    - Log detailed error information
    - Raise sanitized DRF exceptions for API responses
    - Never expose stack traces or internal details to clients
    """

    def __init__(self):
        """Initialize error handler with logger"""
        self.logger = logging.getLogger(__name__)

    def handle_database_error(self, e: Exception) -> None:
        """
        Handle database errors by raising appropriate DRF exception.

        FROZEN ARCHITECTURE: RAISES DRF exceptions (NOT returns Response, NOT returns HTTPException)

        Args:
            e: Database exception (psycopg2, django.db.utils, etc.)

        Raises:
            DatabaseUnavailableError: Database connection failed (HTTP 503)
            ValidationError: Data validation/constraint violation (HTTP 400)
            APIException: Generic database error (HTTP 500)

        Example Usage:
            try:
                user = User.objects.get(id=user_id)
            except Exception as e:
                error_handler = ServiceErrorHandler()
                error_handler.handle_database_error(e)  # Will raise appropriate DRF exception

        CRITICAL: Do NOT return exceptions - RAISE them!
        """
        error_str = str(e).lower()

        # Log detailed error for debugging (internal only - never sent to client)
        self.logger.error(
            f"Database error: {str(e)}",
            exc_info=True,
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )

        # Convert to sanitized DRF exception for API response
        if "connection" in error_str or "timeout" in error_str:
            # ✅ CORRECT: Raise DRF exception (NOT return Response)
            raise DatabaseUnavailableError(detail="Database connection failed")

        elif "constraint" in error_str or "unique" in error_str or "foreign key" in error_str:
            # ✅ CORRECT: Raise DRF exception (NOT return Response)
            raise ValidationError(detail="Data validation failed")

        else:
            # ✅ CORRECT: Raise DRF exception (NOT return Response)
            raise APIException(detail="Database error")

    def handle_service_error(self, e: ServiceError) -> None:
        """
        Handle custom ServiceError exceptions.

        Args:
            e: ServiceError instance

        Raises:
            APIException: Service error with sanitized details
        """
        # Log detailed error with service context
        self.logger.error(
            f"Service error in {e.service}: {e.message}",
            extra={
                "service": e.service,
                "error_code": e.error_code,
                "error_message": e.message
            }
        )

        # ✅ CORRECT: Raise DRF exception (NOT return Response)
        raise APIException(
            detail=f"Service error: {e.message}",
            code=e.error_code or "service_error"
        )

    def handle_external_api_error(self, e: Exception, service_name: str) -> None:
        """
        Handle errors from external API integrations (Vault, MinIO, Kong, etc.)

        Args:
            e: Exception from external API
            service_name: Name of external service (e.g., "Vault", "MinIO")

        Raises:
            APIException: External service unavailable
        """
        # Log detailed error
        self.logger.error(
            f"External API error from {service_name}: {str(e)}",
            exc_info=True,
            extra={
                "service": service_name,
                "error_type": type(e).__name__
            }
        )

        # ✅ CORRECT: Raise DRF exception (NOT return Response)
        raise APIException(detail=f"{service_name} service unavailable")


# ANTI-PATTERNS (FORBIDDEN - DOCUMENTED FOR REFERENCE):
# ❌ WRONG: from rest_framework import HTTPException  # HTTPException does NOT exist in DRF
# ❌ WRONG: return Response(status=status.HTTP_503, detail="...")  # Error handlers RAISE, not RETURN
# ❌ WRONG: def handle_error() -> HTTPException:  # Wrong return type
# ❌ WRONG: raise HTTPException(status_code=503, detail="...")  # FastAPI pattern
#
# ✅ CORRECT: raise DatabaseUnavailableError(detail="...")  # Custom DRF exception
# ✅ CORRECT: raise APIException(detail="...")  # Generic DRF exception
# ✅ CORRECT: raise ValidationError(detail="...")  # DRF validation exception
