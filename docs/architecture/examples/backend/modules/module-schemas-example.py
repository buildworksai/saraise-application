# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Module serializer structure
# backend/src/modules/module_name/serializers.py
# Reference: docs/architecture/application-architecture.md § 4.1 (API Contracts)
# CRITICAL NOTES:
# - DRF Serializers for request/response validation
# - Field constraints: min_length, max_length, regex patterns
# - Type hints: all fields typed (no untyped parameters)
# - Optional fields explicit (Optional[str], with None default)
# - Nested serializers for complex types (e.g., Address, ContactInfo)
# - Enum fields for constrained values (status, type, etc.)
# - Validation: validate_field methods for business logic
# - Documentation: help_text and verbose_name for fields
# - Response serializer: subset of fields (hide internal ids, timestamps)
# Source: docs/architecture/application-architecture.md § 4.1

from rest_framework import serializers
from typing import Optional
from datetime import datetime

class ModuleItemCreateSerializer(serializers.Serializer):
    """Serializer for creating module item"""
    name = serializers.CharField(min_length=1, max_length=255)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate_name(self, value):
        """Validate name field"""
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value

class ModuleItemResponseSerializer(serializers.Serializer):
    """Serializer for module item response"""
    module_id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    class Meta:
        fields = ['module_id', 'name', 'description', 'created_at', 'updated_at']

    # NOTE: No tenant_id field - tenant context is implicit from authenticated user




