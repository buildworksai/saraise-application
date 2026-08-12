"""
Tests for PaymentService.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import razorpay
import stripe
from django.test import TestCase, override_settings

from src.modules.billing_subscriptions.models import Invoice, Payment
from src.modules.billing_subscriptions.services import PaymentService, _stripe_refund_reason


class PaymentServiceTestCase(TestCase):
    """Test cases for PaymentService."""

    def setUp(self):
        """Set up test fixtures."""
        self.tenant_id = str(uuid.uuid4())

        # Create test invoice
        from datetime import timedelta

        from django.utils import timezone

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
                mock_stripe.PaymentIntent.create.assert_called_once_with(
                    amount=10000,
                    currency="usd",
                    description=f"Invoice {self.invoice.invoice_number}",
                    metadata={
                        "invoice_id": str(self.invoice.id),
                        "payment_id": str(self.payment.id),
                        "tenant_id": str(self.payment.tenant_id),
                    },
                    payment_method="pm_test_123",
                    confirmation_method="manual",
                    confirm=True,
                )

                # Verify payment was updated
                self.payment.refresh_from_db()
                self.assertEqual(self.payment.status, "completed")

    def test_process_stripe_payment_without_payment_method_creates_unconfirmed_intent(self):
        """Test Stripe payment intent creation when frontend confirmation is deferred."""
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"

                mock_intent = MagicMock()
                mock_intent.id = "pi_test_123"
                mock_intent.status = "requires_payment_method"
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                result = PaymentService._process_stripe_payment(self.payment, None)

                self.assertFalse(result["success"])
                self.assertEqual(result["transaction_id"], "pi_test_123")
                mock_stripe.PaymentIntent.create.assert_called_once_with(
                    amount=10000,
                    currency="usd",
                    description=f"Invoice {self.invoice.invoice_number}",
                    metadata={
                        "invoice_id": str(self.invoice.id),
                        "payment_id": str(self.payment.id),
                        "tenant_id": str(self.payment.tenant_id),
                    },
                )

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

    def test_process_payment_rejects_unsupported_gateway_without_mutating_payment(self):
        """Test gateway dispatch rejects unknown processors before any state mutation."""
        with self.assertRaisesMessage(ValueError, "Unsupported payment gateway: bank_transfer"):
            PaymentService.process_payment(self.payment, "bank_transfer", "pm_test_123")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.payment.transaction_id, "")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_card_error_marks_payment_failed(self):
        """Test Stripe card errors are normalized and persisted as payment failure."""
        card_error = stripe.error.CardError("Declined by issuer", "card", "card_declined")

        with patch(
            "src.modules.billing_subscriptions.services.stripe.PaymentIntent.create",
            side_effect=card_error,
        ):
            result = PaymentService._process_stripe_payment(self.payment, "pm_declined")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Card error: Declined by issuer")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.payment.transaction_id, "")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_gateway_error_marks_payment_failed(self):
        """Test Stripe SDK errors are returned as Stripe failures and persisted."""
        gateway_error = stripe.error.APIConnectionError("Gateway unavailable")

        with patch(
            "src.modules.billing_subscriptions.services.stripe.PaymentIntent.create",
            side_effect=gateway_error,
        ):
            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Stripe error: Gateway unavailable")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.payment.transaction_id, "")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_unexpected_exception_is_returned_without_completion(self):
        """Test unexpected Stripe processing exceptions do not falsely complete the payment."""
        with patch(
            "src.modules.billing_subscriptions.services.stripe.PaymentIntent.create",
            side_effect=RuntimeError("serializer failure"),
        ):
            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "serializer failure")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.payment.transaction_id, "")

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

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_process_razorpay_payment_requires_configured_credentials(self):
        """Test Razorpay processing fails closed when credentials are absent."""
        result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Razorpay credentials not configured")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.payment.transaction_id, "")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_payment_without_payment_method_returns_frontend_order(self):
        """Test Razorpay order creation returns the handoff payload when capture is deferred."""
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_test_123"}

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_payment(self.payment, None)

        self.assertTrue(result["success"])
        self.assertTrue(result["requires_action"])
        self.assertEqual(result["order_id"], "order_test_123")
        self.assertEqual(result["transaction_id"], "order_test_123")
        mock_client.payment.capture.assert_not_called()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.payment.transaction_id, "order_test_123")
        self.assertEqual(self.payment.payment_method, "razorpay")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_payment_capture_failure_marks_payment_failed(self):
        """Test non-captured Razorpay responses fail the payment with order context."""
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_test_123"}
        mock_client.payment.capture.return_value = {"status": "authorized", "id": "pay_test_123"}

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment capture status: authorized")
        self.assertEqual(result["order_id"], "order_test_123")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.payment.transaction_id, "order_test_123")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_payment_bad_request_marks_payment_failed(self):
        """Test Razorpay capture BadRequest errors are normalized with order context."""
        mock_client = MagicMock()
        mock_client.order.create.return_value = {"id": "order_test_123"}
        mock_client.payment.capture.side_effect = razorpay.errors.BadRequestError("capture rejected")

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment capture failed: capture rejected")
        self.assertEqual(result["order_id"], "order_test_123")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.payment.transaction_id, "order_test_123")

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

    def test_process_stripe_refund_normalizes_reason_for_stripe_contract(self):
        """Test Stripe refund receives only Stripe's allowed reason literals."""
        self.payment.status = "completed"
        self.payment.transaction_id = "pi_test_123"
        self.payment.save(update_fields=["status", "transaction_id"])

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                mock_refund = MagicMock()
                mock_refund.id = "re_test_123"
                mock_stripe.Refund.create.return_value = mock_refund

                result = PaymentService._process_stripe_refund(self.payment, Decimal("25.00"), "fraudulent")

                self.assertTrue(result["success"])
                mock_stripe.Refund.create.assert_called_once_with(
                    payment_intent="pi_test_123",
                    amount=2500,
                    reason="fraudulent",
                )

    def test_process_stripe_refund_defaults_unknown_reason_for_stripe_contract(self):
        """Test unknown refund reasons fail closed to Stripe's customer-requested reason."""
        self.payment.status = "completed"
        self.payment.transaction_id = "pi_test_123"
        self.payment.save(update_fields=["status", "transaction_id"])

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                mock_refund = MagicMock()
                mock_refund.id = "re_test_123"
                mock_stripe.Refund.create.return_value = mock_refund

                result = PaymentService._process_stripe_refund(self.payment, Decimal("25.00"), "merchant_policy")

                self.assertTrue(result["success"])
                mock_stripe.Refund.create.assert_called_once_with(
                    payment_intent="pi_test_123",
                    amount=2500,
                    reason="requested_by_customer",
                )

    def test_stripe_refund_reason_allows_every_stripe_contract_literal(self):
        """Test the Stripe refund allow-list preserves every supported public reason."""
        for reason in ("duplicate", "fraudulent", "requested_by_customer"):
            self.assertEqual(_stripe_refund_reason(reason), reason)

    def test_process_refund_rejects_incomplete_payment_before_gateway_dispatch(self):
        """Test refund orchestration refuses incomplete payments without gateway calls."""
        self.payment.payment_method = "stripe"
        self.payment.save(update_fields=["payment_method"])

        with patch.object(PaymentService, "_process_stripe_refund") as mock_stripe_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment must be completed to refund")
        mock_stripe_refund.assert_not_called()

    def test_process_refund_rejects_unsupported_payment_method(self):
        """Test refund orchestration reports unsupported stored payment methods."""
        self.payment.status = "completed"
        self.payment.payment_method = "bank_transfer"
        self.payment.save(update_fields=["status", "payment_method"])

        result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Unsupported payment method: bank_transfer")

    def test_process_refund_routes_completed_payments_by_method(self):
        """Test refund orchestration delegates completed payments to the stored gateway."""
        self.payment.status = "completed"
        self.payment.payment_method = "stripe"
        self.payment.save(update_fields=["status", "payment_method"])

        with patch.object(
            PaymentService,
            "_process_stripe_refund",
            return_value={"success": True, "refund_id": "re_test_123"},
        ) as mock_stripe_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertEqual(result, {"success": True, "refund_id": "re_test_123"})
        mock_stripe_refund.assert_called_once_with(self.payment, Decimal("10.00"), "duplicate")

        self.payment.payment_method = "razorpay"
        self.payment.save(update_fields=["payment_method"])

        with patch.object(
            PaymentService,
            "_process_razorpay_refund",
            return_value={"success": True, "refund_id": "rfnd_test_123"},
        ) as mock_razorpay_refund:
            result = PaymentService.process_refund(self.payment, Decimal("15.00"), "customer_request")

        self.assertEqual(result, {"success": True, "refund_id": "rfnd_test_123"})
        mock_razorpay_refund.assert_called_once_with(self.payment, Decimal("15.00"), "customer_request")

    @override_settings(STRIPE_SECRET_KEY="")
    def test_process_stripe_refund_requires_configured_secret(self):
        """Test Stripe refunds fail closed when credentials are absent."""
        self.payment.status = "completed"
        self.payment.transaction_id = "pi_test_123"
        self.payment.save(update_fields=["status", "transaction_id"])

        result = PaymentService._process_stripe_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Stripe secret key not configured")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_refund_gateway_error_is_returned_without_refund_status(self):
        """Test Stripe refund errors do not mark the payment refunded."""
        self.payment.status = "completed"
        self.payment.transaction_id = "pi_test_123"
        self.payment.save(update_fields=["status", "transaction_id"])

        with patch(
            "src.modules.billing_subscriptions.services.stripe.Refund.create",
            side_effect=stripe.error.APIConnectionError("Refund gateway unavailable"),
        ):
            result = PaymentService._process_stripe_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Refund gateway unavailable")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_refund_sends_amount_and_reason_notes(self):
        """Test Razorpay refunds send normalized payload and persist refunded status."""
        self.payment.status = "completed"
        self.payment.payment_method = "razorpay"
        self.payment.transaction_id = "pay_test_123"
        self.payment.save(update_fields=["status", "payment_method", "transaction_id"])

        mock_client = MagicMock()
        mock_client.payment.refund.return_value = {"id": "rfnd_test_123"}

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_refund(self.payment, Decimal("12.34"), "duplicate")

        self.assertTrue(result["success"])
        self.assertEqual(result["refund_id"], "rfnd_test_123")
        mock_client.payment.refund.assert_called_once_with(
            "pay_test_123",
            {
                "amount": 1234,
                "speed": "normal",
                "notes": {"reason": "duplicate"},
            },
        )

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "refunded")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_refund_bad_request_is_returned_without_refund_status(self):
        """Test Razorpay refund BadRequest errors do not mark payment refunded."""
        self.payment.status = "completed"
        self.payment.payment_method = "razorpay"
        self.payment.transaction_id = "pay_test_123"
        self.payment.save(update_fields=["status", "payment_method", "transaction_id"])

        mock_client = MagicMock()
        mock_client.payment.refund.side_effect = razorpay.errors.BadRequestError("refund rejected")

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_refund(self.payment, Decimal("10.00"), None)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "refund rejected")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")
