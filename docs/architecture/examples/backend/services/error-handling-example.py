# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Error Handling Example
# backend/src/services/example.py
# Reference: docs/architecture/security-model.md § 4.2 (Error Handling & Logging)

# Proper error handling with custom exceptions
from rest_framework.exceptions import NotFound, APIException
from typing import Union, TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class UserNotFoundError(Exception):
    """Custom exception for user not found scenarios"""
    pass


class UserAlreadyExistsError(Exception):
    """Custom exception for duplicate user scenarios"""
    pass


def get_user_safe(user_id: str) -> Union['User', None]:
    """
    Get user with proper error handling.

    FROZEN ARCHITECTURE: Django/DRF exception pattern (NOT FastAPI HTTPException)

    CRITICAL: Errors must not leak sensitive information.
    Error responses sanitized before return to client.
    See docs/architecture/security-model.md § 4.2.

    Args:
        user_id: User UUID or identifier

    Returns:
        User object if found

    Raises:
        NotFound: User does not exist (DRF exception, returns HTTP 404)
        APIException: Internal server error (DRF exception, returns HTTP 500)

    Example:
        try:
            user = get_user_safe("123e4567-e89b-12d3-a456-426614174000")
        except NotFound:
            # Handle user not found
            pass
    """
    try:
        # Import here to avoid circular dependency
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Query user by ID
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")
        return user

    except UserNotFoundError:
        # ✅ CORRECT: Raise DRF exception (NOT raise Response)
        # DRF will automatically convert to HTTP 404 JSON response
        raise NotFound(detail="User not found")

    except Exception as e:
        # ✅ CORRECT: Raise DRF exception (NOT raise Response)
        # DRF will automatically convert to HTTP 500 JSON response
        # CRITICAL: Do NOT leak exception details to client
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error retrieving user {user_id}: {str(e)}", exc_info=True)

        raise APIException(detail="Internal server error")


# ANTI-PATTERNS (FORBIDDEN - DOCUMENTED FOR REFERENCE):
# ❌ WRONG: from rest_framework import HTTPException  # HTTPException does NOT exist in DRF
# ❌ WRONG: raise Response(status=status.HTTP_404, detail="...")  # Cannot raise Response
# ❌ WRONG: raise HTTPException(status_code=404, detail="...")  # FastAPI pattern
# ❌ WRONG: return Response({"error": "..."}, status=404)  # Services should NOT return Response
#
# ✅ CORRECT: raise NotFound(detail="User not found")  # DRF exception
# ✅ CORRECT: raise PermissionDenied(detail="Access denied")  # DRF exception
# ✅ CORRECT: raise ValidationError(detail="Invalid data")  # DRF exception
