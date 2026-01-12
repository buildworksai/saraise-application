"""
Additional tests for IntegrationService.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from src.modules.integration_platform.models import Integration
from src.modules.integration_platform.services import IntegrationService


class IntegrationServiceAdditionalTestCase(TestCase):
    """Additional test cases for IntegrationService."""

    def setUp(self):
        """Set up test fixtures."""
        self.tenant_id = str(uuid.uuid4())

        self.integration = Integration.objects.create(
            tenant_id=self.tenant_id,
            name="Test Integration",
            integration_type="rest_api",
            config={"base_url": "https://api.example.com"},
        )

    def test_test_database_connection_postgresql(self):
        """Test PostgreSQL database connection testing."""
        connection_string = "postgresql://user:pass@localhost:5432/testdb"

        # Mock the _test_postgresql_connection method directly
        with patch.object(IntegrationService, "_test_postgresql_connection") as mock_test:
            mock_test.return_value = {
                "success": True,
                "message": "PostgreSQL connection successful (version: PostgreSQL 14.0)",
            }

            result = IntegrationService._test_database_connection(
                self.integration, connection_string
            )

            self.assertTrue(result["success"])
            self.assertIn("PostgreSQL", result["message"])

    def test_test_database_connection_mysql(self):
        """Test MySQL database connection testing."""
        connection_string = "mysql://user:pass@localhost:3306/testdb"

        # Mock the _test_mysql_connection method directly
        with patch.object(IntegrationService, "_test_mysql_connection") as mock_test:
            mock_test.return_value = {
                "success": True,
                "message": "MySQL connection successful (version: 8.0.33)",
            }

            result = IntegrationService._test_database_connection(
                self.integration, connection_string
            )

            self.assertTrue(result["success"])
            self.assertIn("MySQL", result["message"])

    def test_pull_data_from_api(self):
        """Test pulling data from REST API."""
        self.integration.config = {
            "base_url": "https://api.example.com",
            "pull_endpoint": "/api/data",
            "pull_method": "GET",
        }
        self.integration.save()

        with patch("src.modules.integration_platform.services.httpx.request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": [{"id": 1, "name": "Test"}]}
            mock_response.raise_for_status.return_value = None
            mock_request.return_value = mock_response

            result = IntegrationService._pull_data(
                self.integration, "test_credential", None
            )

            self.assertTrue(result["success"])

    def test_handle_update_record_success(self):
        """Test successful webhook record update."""
        from src.modules.billing_subscriptions.models import Invoice

        # Create test invoice
        invoice = Invoice.objects.create(
            tenant_id=self.tenant_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            amount=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            status="pending",
            due_date=(timezone.now() + timedelta(days=30)).date(),
        )

        # Create webhook instance with config attribute
        from src.modules.integration_platform.models import Webhook
        from src.modules.integration_platform.services import WebhookProcessor

        webhook = Webhook.objects.create(
            tenant_id=self.tenant_id,
            name="Test Webhook",
            url="https://example.com/webhook",
            events=[],
            secret="test_secret",
            created_by=str(uuid.uuid4()),
        )
        # Add config as attribute (not a model field)
        webhook.config = {
            "handler_type": "update_record",
            "model": "billing_subscriptions.Invoice",
            "allowed_models": ["billing_subscriptions.Invoice"],
        }

        payload = {"id": str(invoice.id), "status": "paid"}

        result = WebhookProcessor.process_webhook(webhook, payload)

        self.assertTrue(result["success"])

        # Verify invoice was updated
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")

    def test_handle_update_record_tenant_isolation(self):
        """Test that webhook updates enforce tenant isolation."""
        from src.modules.billing_subscriptions.models import Invoice
        from src.modules.integration_platform.models import Webhook
        from src.modules.integration_platform.services import WebhookProcessor

        # Create invoice for different tenant
        other_tenant_id = str(uuid.uuid4())
        invoice = Invoice.objects.create(
            tenant_id=other_tenant_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            amount=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            status="pending",
            due_date=(timezone.now() + timedelta(days=30)).date(),
        )

        # Create webhook for different tenant
        webhook = Webhook.objects.create(
            tenant_id=self.tenant_id,  # Different tenant
            name="Test Webhook",
            url="https://example.com/webhook",
            events=[],
            secret="test_secret",
            created_by=str(uuid.uuid4()),
        )
        # Add config as attribute (not a model field)
        webhook.config = {
            "handler_type": "update_record",
            "model": "billing_subscriptions.Invoice",
            "allowed_models": ["billing_subscriptions.Invoice"],
        }

        payload = {"id": str(invoice.id), "status": "paid"}

        result = WebhookProcessor.process_webhook(webhook, payload)

        # Should fail due to tenant mismatch
        self.assertFalse(result.get("success", True))

        # Verify invoice was NOT updated
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "pending")
