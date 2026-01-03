# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Kong API Gateway Integration
# backend/src/services/kong_service.py
# Reference: docs/architecture/operational-runbooks.md § 3.1 (API Gateway)

import httpx
from src.core.urls import get_kong_url
from rest_framework.exceptions import APIException, ValidationError
from rest_framework import status

class KongService:
    """Kong API Gateway integration service.
    
    CRITICAL: Platform-level infrastructure service.
    Kong handles rate limiting, authentication, and request routing.
    See docs/architecture/operational-runbooks.md § 3.1.
    """
    
    def __init__(self):
        self.kong_url = get_kong_url()
        self.timeout = 30

    def call_api(self, endpoint: str, method: str = "GET", data: dict = None):
        """Call API through Kong with error handling"""
        url = f"{self.kong_url}/api{endpoint}"

        with httpx.Client(timeout=self.timeout) as client:
            try:
                response = client.request(
                    method=method,
                    url=url,
                    json=data,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # ✅ CORRECT: Raise DRF exception (NOT raise Response, NOT HTTPException)
                if e.response.status_code == 400:
                    raise ValidationError(detail=e.response.text)
                else:
                    raise APIException(detail=e.response.text)
            except httpx.TimeoutException:
                # ✅ CORRECT: Raise DRF exception (NOT raise Response, NOT HTTPException)
                raise APIException(detail="Gateway timeout")

