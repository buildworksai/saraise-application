# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Django REST Framework Standards Example
# backend/src/api/routes/example.py
# Reference: docs/architecture/application-architecture.md § 4.1 (API Routes)

# Proper Django REST Framework structure with type safety and validation
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from typing import Optional, List

class UserCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class UserResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    email = serializers.EmailField()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_user(request):
    """Create new user with proper validation.
    
    CRITICAL: All routes must implement authorization via Policy Engine.
    See docs/architecture/application-architecture.md § 4.1.
    """
    serializer = UserCreateSerializer(data=request.data)
    if serializer.is_valid():
        # Implement user creation logic with proper authorization check
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

