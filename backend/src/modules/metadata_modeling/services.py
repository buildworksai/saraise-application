from django.core.exceptions import ValidationError
from typing import Dict, Any, List
from .models import EntityDefinition, FieldDefinition, DynamicResource
import re
from datetime import datetime


class MetadataService:
    """
    Handles schema validation and data processing for Dynamic Resources.
    """

    def validate_data(self, entity_def: EntityDefinition, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates JSON data against the Entity's FieldDefinitions.
        Returns cleaned data or raises ValidationError.
        """
        cleaned_data = {}
        errors = {}

        # Prefetch fields
        fields = {f.key: f for f in entity_def.fields.all()}

        # Check for unknown fields? (Optional, skipping for flexibility/NoSQL nature)
        # Check required fields and types
        for key, field_def in fields.items():
            value = data.get(key)

            # Check Required
            if field_def.is_required and value in [None, ""]:
                errors[key] = "This field is required."
                continue

            if value is None:
                cleaned_data[key] = None
                continue

            # Type Validation & Conversion
            try:
                if field_def.field_type == "number":
                    if not isinstance(value, (int, float)):
                        try:
                            value = float(value)
                        except (ValueError, TypeError):
                            errors[key] = "Must be a number."
                            continue

                elif field_def.field_type == "boolean":
                    if not isinstance(value, bool):
                        errors[key] = "Must be a boolean."
                        continue

                elif field_def.field_type == "date":
                    # Expect ISO format YYYY-MM-DD
                    if not isinstance(value, str):  # Simple check
                        errors[key] = "Must be a date string."
                        continue

                elif field_def.field_type == "select":
                    if value not in field_def.options:
                        errors[key] = f"Invalid option. Must be one of: {', '.join(field_def.options)}"
                        continue

            except Exception as e:
                errors[key] = f"Validation error: {str(e)}"
                continue

            cleaned_data[key] = value

        if errors:
            raise ValidationError(errors)

        return cleaned_data
