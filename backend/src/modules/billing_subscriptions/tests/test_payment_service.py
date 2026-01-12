"""
Tests for PaymentService.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from decimal import Decimal
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from src.modules.billing_subscriptions.models import Invoice, Payment
from src.modules.billing_subscriptions.services import PaymentService


class PaymentServiceTestCase(TestCase):
    """Test cases for PaymentService."""

    def setUp(self):
        """Set up test fixtures."""
        self.tenant_id = str(uuid.uuid4())

        # Create test invoice
        from django.utils import timezone
        from datetime import timedelta

        self.invoice = Invoice.objects.create(
            tenant_id=self.tenant_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:8]}",
            amount=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            status="pending",
            due_date=(timezone.now() + timedelta(days=30)).date(),
        )

        # Create test payment
        self.payment = Payment.objects.create(
            tenant_id=self.tenant_id,
            invoice=self.invoice,
            amount=Decimal("100.00"),
            payment_method="stripe",
            status="pending",
        )

    def test_process_stripe_payment_success(self):
        """Test successful Stripe payment processing."""
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                
                mock_intent = MagicMock()
                mock_intent.id = "pi_test_123"
                mock_intent.status = "succeeded"
                mock_intent.client_secret = None
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

                self.assertTrue(result["success"])
                self.assertEqual(result["transaction_id"], "pi_test_123")

                # Verify payment was updated
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, "completed")

    def test_process_stripe_payment_requires_action(self):
        """Test Stripe payment requiring 3D Secure."""
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                
                mock_intent = MagicMock()
                mock_intent.id = "pi_test_123"
                mock_intent.status = "requires_action"
                mock_intent.client_secret = "pi_test_123_secret"
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

                self.assertFalse(result["success"])
                self.assertTrue(result.get("requires_action"))
                self.assertIsNotNone(result.get("client_secret"))

    def test_process_razorpay_payment_success(self):
        """Test successful Razorpay payment processing."""
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                
                mock_client = MagicMock()
                mock_order = {"id": "order_test_123"}
                mock_client.order.create.return_value = mock_order

                mock_payment_capture = {"status": "captured", "id": "pay_test_123"}
                mock_client.payment.capture.return_value = mock_payment_capture

                mock_razorpay.Client.return_value = mock_client

                result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

                self.assertTrue(result["success"])
                self.assertEqual(result["transaction_id"], "pay_test_123")

                # Verify payment was updated
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, "completed")

    def test_verify_stripe_webhook_signature(self):
        """Test Stripe webhook signature verification."""
        payload = b'{"type":"payment_intent.succeeded"}'
        signature = "test_signature"

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test_123"
                
                mock_webhook = MagicMock()
                mock_webhook.construct_event.return_value = {"type": "payment_intent.succeeded"}
                mock_stripe.Webhook = mock_webhook

                result = PaymentService._verify_stripe_signature(payload, signature)

                self.assertTrue(result)

    def test_verify_razorpay_webhook_signature(self):
        """Test Razorpay webhook signature verification."""
        import hashlib
        import hmac

        payload = b'{"event":"payment.captured"}'
        secret = "test_secret"
        expected_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
            mock_settings.RAZORPAY_WEBHOOK_SECRET = secret

            result = PaymentService._verify_razorpay_signature(payload, expected_signature)

            self.assertTrue(result)
