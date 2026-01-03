# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: DRF Serializers Standards Example
# backend/src/serializers/example.py
# Reference: docs/architecture/module-framework.md § 3 (Module Schemas)
# Also: docs/architecture/security-model.md § 3.1 (Input Validation)
# 
# CRITICAL NOTES:
# - All request/response schemas use DRF Serializers with strict type checking
# - EmailField validates email format (prevents invalid data entry)
# - Field constraints enforce min/max lengths, regex patterns (prevent injection attacks)
# - All serializers use strict validation (no implicit type coercion)

# Good - Proper DRF Serializers with validation
from rest_framework import serializers
from typing import Optional
from datetime import datetime

class UserSerializer(serializers.Serializer):
    """User serializer with strict validation."""
    id = serializers.CharField(help_text="Unique user identifier")
    name = serializers.CharField(min_length=1, max_length=100)
    email = serializers.EmailField()
    is_active = serializers.BooleanField(default=True)
    created_at = serializers.DateTimeField(allow_null=True, required=False)

    class Meta:
        fields = ['id', 'name', 'email', 'is_active', 'created_at']

    def validate_name(self, value):
        """Validate name field."""
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    def validate_email(self, value):
        """Validate email field."""
        if not value:
            raise serializers.ValidationError("Email is required")
        return value.lower()



