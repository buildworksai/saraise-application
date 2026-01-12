from django.test import TestCase
from django.core.exceptions import ValidationError
from ..models import EntityDefinition, FieldDefinition
from ..services import MetadataService
import uuid


class ValidationTestCase(TestCase):
    def setUp(self):
        self.tenant_id = uuid.uuid4()
        self.entity = EntityDefinition.objects.create(tenant_id=self.tenant_id, name="Vehicle", code="vehicle")
        self.service = MetadataService()

    def test_basic_validation(self):
        FieldDefinition.objects.create(
            tenant_id=self.tenant_id,
            entity_definition=self.entity,
            name="Make",
            key="make",
            field_type="text",
            is_required=True,
        )
        FieldDefinition.objects.create(
            tenant_id=self.tenant_id,
            entity_definition=self.entity,
            name="Year",
            key="year",
            field_type="number",
            is_required=True,
        )

        # Valid
        valid_data = {"make": "Toyota", "year": 2020}
        cleaned = self.service.validate_data(self.entity, valid_data)
        self.assertEqual(cleaned["make"], "Toyota")
        self.assertEqual(cleaned["year"], 2020.0)

        # Invalid (Type)
        invalid_data = {"make": "Toyota", "year": "NotANumber"}
        with self.assertRaises(ValidationError) as cm:
            self.service.validate_data(self.entity, invalid_data)
        self.assertIn("year", cm.exception.message_dict)

        # Invalid (Required)
        missing_data = {"year": 2020}
        with self.assertRaises(ValidationError) as cm:
            self.service.validate_data(self.entity, missing_data)
        self.assertIn("make", cm.exception.message_dict)

    def test_select_validation(self):
        FieldDefinition.objects.create(
            tenant_id=self.tenant_id,
            entity_definition=self.entity,
            name="Color",
            key="color",
            field_type="select",
            options=["Red", "Blue"],
        )

        # Valid
        self.service.validate_data(self.entity, {"color": "Red"})

        # Invalid Option
        with self.assertRaises(ValidationError):
            self.service.validate_data(self.entity, {"color": "Green"})
