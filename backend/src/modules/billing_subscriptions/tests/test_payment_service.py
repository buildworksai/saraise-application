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
    def test_process_payment_dispatches_to_stripe_gateway(self):
        """Test the public dispatcher routes 'stripe' through the Stripe path (default gateway)."""
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"

                mock_intent = MagicMock()
                mock_intent.id = "pi_dispatch_123"
                mock_intent.status = "succeeded"
                mock_intent.client_secret = None
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                result = PaymentService.process_payment(self.payment, "stripe", "pm_test_123")

        self.assertTrue(result["success"])
        self.assertEqual(result["transaction_id"], "pi_dispatch_123")

    def test_process_payment_default_gateway_is_stripe(self):
        """Test omitting the gateway argument defaults to Stripe, not silently no-oping."""
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"

                mock_intent = MagicMock()
                mock_intent.id = "pi_default_123"
                mock_intent.status = "succeeded"
                mock_intent.client_secret = None
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                result = PaymentService.process_payment(self.payment)

        self.assertTrue(result["success"])
        self.assertEqual(result["transaction_id"], "pi_default_123")

    def test_process_payment_dispatches_to_razorpay_gateway(self):
        """Test the public dispatcher routes 'razorpay' through the Razorpay path."""
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"

                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_dispatch_123"}
                mock_razorpay.Client.return_value = mock_client

                result = PaymentService.process_payment(self.payment, "razorpay", None)

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "order_dispatch_123")

    def test_verify_webhook_signature_dispatches_to_stripe(self):
        """Test the public webhook dispatcher routes 'stripe' to the Stripe verifier."""
        payload = b'{"type":"payment_intent.succeeded"}'
        signature = "test_signature"

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test_123"
                mock_stripe.Webhook.construct_event.return_value = {"type": "payment_intent.succeeded"}

                result = PaymentService.verify_webhook_signature(payload, signature, "stripe")

        self.assertTrue(result)

    def test_verify_webhook_signature_default_gateway_is_stripe(self):
        """Test omitting the gateway argument defaults webhook verification to Stripe."""
        payload = b'{"type":"payment_intent.succeeded"}'
        signature = "test_signature"

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test_123"
                mock_stripe.Webhook.construct_event.return_value = {"type": "payment_intent.succeeded"}

                result = PaymentService.verify_webhook_signature(payload, signature)

        self.assertTrue(result)

    def test_verify_webhook_signature_dispatches_to_razorpay(self):
        """Test the public webhook dispatcher routes 'razorpay' to the Razorpay verifier."""
        import hashlib
        import hmac

        payload = b'{"event":"payment.captured"}'
        secret = "test_secret"
        expected_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
            mock_settings.RAZORPAY_WEBHOOK_SECRET = secret

            result = PaymentService.verify_webhook_signature(payload, expected_signature, "razorpay")

        self.assertTrue(result)

    def test_verify_webhook_signature_rejects_unknown_gateway(self):
        """Test the public webhook dispatcher fails closed for unsupported gateways."""
        result = PaymentService.verify_webhook_signature(b"payload", "sig", "bank_transfer")

        self.assertFalse(result)

    @override_settings(STRIPE_WEBHOOK_SECRET="")
    def test_verify_stripe_signature_fails_closed_without_configured_secret(self):
        """Test Stripe webhook verification fails closed when no secret is configured."""
        result = PaymentService._verify_stripe_signature(b"payload", "sig")

        self.assertFalse(result)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_123")
    def test_verify_stripe_signature_rejects_value_error(self):
        """Test malformed Stripe payloads (ValueError) are rejected, not raised."""
        with patch(
            "src.modules.billing_subscriptions.services.stripe.Webhook.construct_event",
            side_effect=ValueError("invalid payload"),
        ):
            result = PaymentService._verify_stripe_signature(b"bad payload", "sig")

        self.assertFalse(result)

    @override_settings(STRIPE_WEBHOOK_SECRET="whsec_test_123")
    def test_verify_stripe_signature_rejects_signature_verification_error(self):
        """Test Stripe SignatureVerificationError is rejected, not raised."""
        sig_error = stripe.error.SignatureVerificationError("bad signature", "sig_header")
        with patch(
            "src.modules.billing_subscriptions.services.stripe.Webhook.construct_event",
            side_effect=sig_error,
        ):
            result = PaymentService._verify_stripe_signature(b"payload", "bad_sig")

        self.assertFalse(result)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_verify_razorpay_signature_fails_closed_without_configured_secret(self):
        """Test Razorpay webhook verification fails closed when no secret is configured."""
        result = PaymentService._verify_razorpay_signature(b"payload", "sig")

        self.assertFalse(result)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="test_secret")
    def test_verify_razorpay_signature_rejects_mismatched_signature(self):
        """Test Razorpay verification rejects a signature that doesn't match the computed HMAC."""
        result = PaymentService._verify_razorpay_signature(b'{"event":"payment.captured"}', "not_the_real_signature")

        self.assertFalse(result)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="test_secret")
    def test_verify_razorpay_signature_swallows_unexpected_exception(self):
        """Test unexpected errors computing the Razorpay HMAC are swallowed and fail closed."""
        with patch(
            "src.modules.billing_subscriptions.services.hmac.new",
            side_effect=RuntimeError("hmac backend unavailable"),
        ):
            result = PaymentService._verify_razorpay_signature(b"payload", "sig")

        self.assertFalse(result)

    def test_process_razorpay_payment_swallows_unexpected_exception(self):
        """Test a non-BadRequestError failure during Razorpay order creation is caught and returned."""
        with patch(
            "src.modules.billing_subscriptions.services.razorpay.Client",
            side_effect=RuntimeError("network unreachable"),
        ):
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"

                result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "network unreachable")

    def test_process_razorpay_payment_bad_request_at_order_creation_marks_payment_failed(self):
        """Test a Razorpay BadRequestError raised while creating the order (not capturing) is handled."""
        with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
            mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
            mock_settings.RAZORPAY_KEY_SECRET = "secret_123"

            mock_client = MagicMock()
            mock_client.order.create.side_effect = razorpay.errors.BadRequestError("invalid order request")

            with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
                result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Razorpay error: invalid order request")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    def test_process_razorpay_refund_requires_configured_credentials(self):
        """Test Razorpay refunds fail closed when credentials are absent."""
        self.payment.status = "completed"
        self.payment.payment_method = "razorpay"
        self.payment.transaction_id = "pay_test_123"
        self.payment.save(update_fields=["status", "payment_method", "transaction_id"])

        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
            result = PaymentService._process_razorpay_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Razorpay credentials not configured")

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")

    def test_process_stripe_payment_fails_closed_without_configured_secret(self):
        """Test _process_stripe_payment itself (not just refund) fails closed when unconfigured.

        Defeats a ReplaceFalseWithTrue mutant on the returned success flag.
        """
        with override_settings(STRIPE_SECRET_KEY=""):
            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertIs(result["success"], False)
        self.assertEqual(result["error"], "Stripe secret key not configured")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_logs_traceback_on_unexpected_exception(self):
        """Test the unexpected-exception logger call requests a traceback (exc_info=True).

        Defeats a ReplaceTrueWithFalse mutant on the exc_info kwarg -- the returned
        result is identical either way, so only a direct logger-call assertion can
        distinguish the two.
        """
        with patch(
            "src.modules.billing_subscriptions.services.stripe.PaymentIntent.create",
            side_effect=RuntimeError("boom"),
        ):
            with patch("src.modules.billing_subscriptions.services.logger") as mock_logger:
                PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        mock_logger.error.assert_called_once()
        self.assertTrue(mock_logger.error.call_args.kwargs.get("exc_info"))

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_status_check_is_exact_equality_not_dynamic(self):
        """Test the 'succeeded' status check uses true equality, not identity.

        Uses a dynamically constructed (non-interned) copy of the string "succeeded"
        so an `==` -> `is` mutant on `intent.status == "succeeded"` is exposed: under
        the mutant, two equal-but-distinct string objects would compare unequal via
        `is`, wrongly routing to the failure branch.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_dynamic_123"
            mock_intent.status = "".join(["succ", "eeded"])
            mock_intent.client_secret = None
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertTrue(result["success"])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_status_check_rejects_prefix_superset(self):
        """Test a status that lexically sorts after 'succeeded' (but isn't equal) is
        NOT treated as success -- defeats an `==` -> `>=` mutant.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_super_123"
            mock_intent.status = "succeededx"
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment intent status: succeededx")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_requires_action_check_is_exact_equality(self):
        """Test the 'requires_action' branch uses true equality, not identity, via a
        dynamically constructed (non-interned) copy of the string.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_ra_dynamic_123"
            mock_intent.status = "".join(["requires", "_action"])
            mock_intent.client_secret = "client-value-ra"  # pragma: allowlist secret
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertTrue(result.get("requires_action"))
        self.assertEqual(result.get("client_secret"), "client-value-ra")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_requires_action_check_rejects_lexically_smaller_status(self):
        """Test a status that sorts before 'requires_action' (and is not 'succeeded')
        falls through to the generic failure branch -- defeats an `==` -> `<=` mutant.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_lt_123"
            mock_intent.status = "aaaa"
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertNotIn("requires_action", result)
        self.assertEqual(result["error"], "Payment intent status: aaaa")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_requires_action_check_rejects_lexically_larger_status(self):
        """Test a status that sorts after 'requires_action' (and is not 'succeeded')
        falls through to the generic failure branch -- defeats an `==` -> `>=` mutant.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_gt_123"
            mock_intent.status = "requires_actionx"
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertFalse(result["success"])
        self.assertNotIn("requires_action", result)
        self.assertEqual(result["error"], "Payment intent status: requires_actionx")

    @override_settings(STRIPE_SECRET_KEY="sk_test_123")
    def test_process_stripe_payment_success_passes_through_real_client_secret(self):
        """Test a successful payment's client_secret is the intent's actual value, not
        unconditionally None -- defeats an AddNot mutant on
        `hasattr(intent, "client_secret")`, which would force client_secret to None
        even when the attribute is genuinely present.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            mock_intent = MagicMock()
            mock_intent.id = "pi_secret_123"
            mock_intent.status = "succeeded"
            mock_intent.client_secret = "client-value-success"  # pragma: allowlist secret
            mock_stripe.PaymentIntent.create.return_value = mock_intent

            result = PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        self.assertTrue(result["success"])
        self.assertEqual(result["client_secret"], "client-value-success")

    def test_process_stripe_payment_falls_back_to_usd_for_falsy_invoice_currency(self):
        """Test the `or "USD"` fallback actually engages for a falsy (empty string)
        currency -- defeats an `or` -> `and` mutant, which would leave currency empty.
        """
        self.invoice.currency = ""  # not a real model field; exercises getattr fallback path
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                mock_intent = MagicMock()
                mock_intent.id = "pi_currency_123"
                mock_intent.status = "succeeded"
                mock_intent.client_secret = None
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                PaymentService._process_stripe_payment(self.payment, "pm_test_123")

        mock_stripe.PaymentIntent.create.assert_called_once()
        self.assertEqual(mock_stripe.PaymentIntent.create.call_args.kwargs["currency"], "usd")

    def test_process_payment_dispatch_requires_exact_equality_to_stripe(self):
        """Test the dispatcher's 'stripe' branch uses true equality, not identity.

        Uses a dynamically constructed gateway string equal to, but not the same
        object as, the "stripe" literal in services.py -- defeats an `==` -> `is`
        mutant that would wrongly fall through to the unsupported-gateway branch.
        """
        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                mock_intent = MagicMock()
                mock_intent.id = "pi_dyn_dispatch_123"
                mock_intent.status = "succeeded"
                mock_intent.client_secret = None
                mock_stripe.PaymentIntent.create.return_value = mock_intent

                dynamic_gateway = "".join(["str", "ipe"])
                result = PaymentService.process_payment(self.payment, dynamic_gateway, "pm_test_123")

        self.assertTrue(result["success"])

    def test_process_payment_dispatch_rejects_gateway_lexically_after_stripe(self):
        """Test a gateway lexically greater than 'stripe' (not equal) is rejected as
        unsupported -- defeats an `==` -> `>=` mutant on the 'stripe' branch.
        """
        with self.assertRaisesMessage(ValueError, "Unsupported payment gateway: stripey"):
            PaymentService.process_payment(self.payment, "stripey", "pm_test_123")

    def test_process_payment_dispatch_requires_exact_equality_to_razorpay(self):
        """Test the dispatcher's 'razorpay' branch uses true equality, not identity,
        via a dynamically constructed gateway string.
        """
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_dyn_123"}
                mock_razorpay.Client.return_value = mock_client

                dynamic_gateway = "".join(["razor", "pay"])
                result = PaymentService.process_payment(self.payment, dynamic_gateway, None)

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "order_dyn_123")

    def test_process_payment_dispatch_rejects_gateway_lexically_after_both_known_gateways(self):
        """Test a gateway lexically greater than both 'stripe' and 'razorpay' is
        rejected -- defeats an `==` -> `>=` mutant on the 'razorpay' elif branch.
        """
        with self.assertRaisesMessage(ValueError, "Unsupported payment gateway: zzzzzzz"):
            PaymentService.process_payment(self.payment, "zzzzzzz", "pm_test_123")

    def test_process_razorpay_payment_computes_exact_amount_in_paise(self):
        """Test the amount * 100 conversion is exact -- defeats every ReplaceBinaryOperator
        mutant on `*` (pow/add/floordiv/div/sub/mod) and every NumberReplacer mutant on
        the literal 100, since each produces a value different from 200 for amount=2.00.
        """
        self.payment.amount = Decimal("2.00")
        self.payment.save(update_fields=["amount"])

        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_amount_123"}
                mock_client.payment.capture.return_value = {"status": "captured", "id": "pay_amount_123"}
                mock_razorpay.Client.return_value = mock_client

                PaymentService._process_razorpay_payment(self.payment, "pay_amount_123")

        _, order_kwargs = mock_client.order.create.call_args
        self.assertEqual(order_kwargs["data"]["amount"], 200)
        _, capture_data = mock_client.payment.capture.call_args.args
        self.assertEqual(capture_data["amount"], 200)

    def test_process_razorpay_payment_credentials_check_requires_both_missing_is_or(self):
        """Test that a single missing Razorpay credential (not both) is still rejected --
        defeats an `or` -> `and` mutant on `not key_id or not key_secret`.
        """
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="secret_123"):
            result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Razorpay credentials not configured")

    def test_process_razorpay_payment_falls_back_to_usd_for_falsy_invoice_currency(self):
        """Test the Razorpay `or "USD"` currency fallback engages for a falsy value --
        defeats an `or` -> `and` mutant.
        """
        self.invoice.currency = ""
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_curr_123"}
                mock_razorpay.Client.return_value = mock_client

                PaymentService._process_razorpay_payment(self.payment, None)

        _, order_kwargs = mock_client.order.create.call_args
        self.assertEqual(order_kwargs["data"]["currency"], "USD")

    def test_process_razorpay_payment_capture_status_check_is_exact_equality(self):
        """Test the 'captured' status check uses true equality, not identity, via a
        dynamically constructed (non-interned) copy of the string.
        """
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_dyn_cap_123"}
                mock_client.payment.capture.return_value = {"status": "".join(["capt", "ured"])}
                mock_razorpay.Client.return_value = mock_client

                result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertTrue(result["success"])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "completed")

    def test_process_razorpay_payment_capture_status_check_rejects_prefix_superset(self):
        """Test a capture status lexically after 'captured' (not equal) is rejected --
        defeats an `==` -> `>=` mutant.
        """
        with patch("src.modules.billing_subscriptions.services.razorpay") as mock_razorpay:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.RAZORPAY_KEY_ID = "rzp_test_123"
                mock_settings.RAZORPAY_KEY_SECRET = "secret_123"
                mock_client = MagicMock()
                mock_client.order.create.return_value = {"id": "order_gt_cap_123"}
                mock_client.payment.capture.return_value = {"status": "capturedx"}
                mock_razorpay.Client.return_value = mock_client

                result = PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment capture status: capturedx")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "failed")

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_payment_logs_traceback_on_unexpected_exception(self):
        """Test the unexpected-exception logger call for Razorpay requests a traceback
        (exc_info=True) -- defeats a ReplaceTrueWithFalse mutant.
        """
        with patch(
            "src.modules.billing_subscriptions.services.razorpay.Client",
            side_effect=RuntimeError("boom"),
        ):
            with patch("src.modules.billing_subscriptions.services.logger") as mock_logger:
                PaymentService._process_razorpay_payment(self.payment, "pay_test_123")

        mock_logger.error.assert_called_once()
        self.assertTrue(mock_logger.error.call_args.kwargs.get("exc_info"))

    def test_verify_webhook_signature_dispatch_requires_exact_equality_to_stripe(self):
        """Test the webhook dispatcher's 'stripe' branch uses true equality, not
        identity, via a dynamically constructed gateway string.
        """
        payload = b'{"type":"payment_intent.succeeded"}'
        signature = "test_signature"

        with patch("src.modules.billing_subscriptions.services.stripe") as mock_stripe:
            with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test_123"
                mock_stripe.Webhook.construct_event.return_value = {"type": "payment_intent.succeeded"}

                dynamic_gateway = "".join(["str", "ipe"])
                result = PaymentService.verify_webhook_signature(payload, signature, dynamic_gateway)

        self.assertTrue(result)

    def test_verify_webhook_signature_dispatch_rejects_gateway_lexically_after_stripe(self):
        """Test a gateway lexically greater than 'stripe' is rejected, not routed to
        the Stripe verifier -- defeats an `==` -> `>=` mutant on the 'stripe' branch.

        Patches both private verifiers to return True unconditionally, so only the
        routing decision (not verifier fail-closed behavior) can produce a True result.
        """
        with patch.object(PaymentService, "_verify_stripe_signature", return_value=True):
            with patch.object(PaymentService, "_verify_razorpay_signature", return_value=True):
                result = PaymentService.verify_webhook_signature(b"payload", "sig", "stripey")

        self.assertFalse(result)

    def test_verify_webhook_signature_dispatch_requires_exact_equality_to_razorpay(self):
        """Test the webhook dispatcher's 'razorpay' branch uses true equality, not
        identity, via a dynamically constructed gateway string.
        """
        import hashlib
        import hmac

        payload = b'{"event":"payment.captured"}'
        secret = "test_secret"
        expected_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        with patch("src.modules.billing_subscriptions.services.settings") as mock_settings:
            mock_settings.RAZORPAY_WEBHOOK_SECRET = secret

            dynamic_gateway = "".join(["razor", "pay"])
            result = PaymentService.verify_webhook_signature(payload, expected_signature, dynamic_gateway)

        self.assertTrue(result)

    def test_verify_webhook_signature_dispatch_rejects_gateway_lexically_after_both(self):
        """Test a gateway lexically greater than both known gateways is rejected --
        defeats an `==` -> `>=` mutant on the 'razorpay' elif branch.

        Patches both private verifiers to return True unconditionally, so only the
        routing decision (not verifier fail-closed behavior) can produce a True result.
        """
        with patch.object(PaymentService, "_verify_stripe_signature", return_value=True):
            with patch.object(PaymentService, "_verify_razorpay_signature", return_value=True):
                result = PaymentService.verify_webhook_signature(b"payload", "sig", "zzzzzzz")

        self.assertFalse(result)

    def test_verify_webhook_signature_dispatch_rejects_gateway_lexically_before_razorpay(self):
        """Test a gateway lexically less than 'razorpay' (and not 'stripe') is
        rejected, not routed to the Razorpay verifier -- defeats an `==` -> `<=`
        mutant on the 'razorpay' elif branch.

        Patches both private verifiers to return True unconditionally, so only the
        routing decision (not verifier fail-closed behavior) can produce a True result.
        """
        with patch.object(PaymentService, "_verify_stripe_signature", return_value=True):
            with patch.object(PaymentService, "_verify_razorpay_signature", return_value=True):
                result = PaymentService.verify_webhook_signature(b"payload", "sig", "aaaa")

        self.assertFalse(result)

    def test_process_refund_status_guard_is_exact_equality_not_dynamic(self):
        """Test the 'completed' guard in process_refund uses true equality, not
        identity, via a dynamically constructed (non-interned) copy of the string --
        defeats an `!=` -> `is not` mutant, which would wrongly reject a dynamically
        built but content-equal status.
        """
        self.payment.status = "".join(["complet", "ed"])
        self.payment.payment_method = "stripe"
        self.payment.save(update_fields=["status", "payment_method"])

        with patch.object(
            PaymentService,
            "_process_stripe_refund",
            return_value={"success": True, "refund_id": "re_dyn_123"},
        ) as mock_stripe_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertEqual(result, {"success": True, "refund_id": "re_dyn_123"})
        mock_stripe_refund.assert_called_once()

    def test_process_refund_status_guard_rejects_lexically_smaller_status(self):
        """Test a status lexically before 'completed' (and not equal) is still
        rejected -- defeats a `!=` -> `>` mutant, which would wrongly let smaller
        values through to gateway dispatch.
        """
        self.payment.status = "aaaa"
        self.payment.payment_method = "stripe"
        self.payment.save(update_fields=["status", "payment_method"])

        with patch.object(PaymentService, "_process_stripe_refund") as mock_stripe_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Payment must be completed to refund")
        mock_stripe_refund.assert_not_called()

    def test_process_refund_payment_method_dispatch_requires_exact_equality_to_stripe(self):
        """Test the refund dispatcher's 'stripe' branch uses true equality, not
        identity, via a dynamically constructed payment_method string.
        """
        self.payment.status = "completed"
        self.payment.payment_method = "".join(["str", "ipe"])
        self.payment.save(update_fields=["status", "payment_method"])

        with patch.object(
            PaymentService,
            "_process_stripe_refund",
            return_value={"success": True, "refund_id": "re_dyn_dispatch_123"},
        ) as mock_stripe_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertEqual(result, {"success": True, "refund_id": "re_dyn_dispatch_123"})
        mock_stripe_refund.assert_called_once()

    def test_process_refund_payment_method_dispatch_rejects_lexically_after_stripe(self):
        """Test a payment_method lexically after 'stripe' (not equal) is rejected as
        unsupported -- defeats an `==` -> `>=` mutant.
        """
        self.payment.status = "completed"
        self.payment.payment_method = "stripey"
        self.payment.save(update_fields=["status", "payment_method"])

        result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Unsupported payment method: stripey")

    def test_process_refund_payment_method_dispatch_requires_exact_equality_to_razorpay(self):
        """Test the refund dispatcher's 'razorpay' branch uses true equality, not
        identity, via a dynamically constructed payment_method string.
        """
        self.payment.status = "completed"
        self.payment.payment_method = "".join(["razor", "pay"])
        self.payment.save(update_fields=["status", "payment_method"])

        with patch.object(
            PaymentService,
            "_process_razorpay_refund",
            return_value={"success": True, "refund_id": "rfnd_dyn_dispatch_123"},
        ) as mock_razorpay_refund:
            result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertEqual(result, {"success": True, "refund_id": "rfnd_dyn_dispatch_123"})
        mock_razorpay_refund.assert_called_once()

    def test_process_refund_payment_method_dispatch_rejects_lexically_after_both(self):
        """Test a payment_method lexically after both known methods is rejected --
        defeats an `==` -> `>=` mutant on the 'razorpay' elif branch.
        """
        self.payment.status = "completed"
        self.payment.payment_method = "zzzzzzz"
        self.payment.save(update_fields=["status", "payment_method"])

        result = PaymentService.process_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Unsupported payment method: zzzzzzz")

    def test_process_razorpay_refund_credentials_check_requires_both_missing_is_or(self):
        """Test that a single missing Razorpay credential (not both) is still rejected
        for refunds -- defeats an `or` -> `and` mutant.
        """
        self.payment.status = "completed"
        self.payment.payment_method = "razorpay"
        self.payment.transaction_id = "pay_test_123"
        self.payment.save(update_fields=["status", "payment_method", "transaction_id"])

        with override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET=""):
            result = PaymentService._process_razorpay_refund(self.payment, Decimal("10.00"), "duplicate")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Razorpay credentials not configured")

    def test_all_payment_service_gateway_methods_remain_static(self):
        """Test every PaymentService gateway method keeps its @staticmethod contract.

        Removing @staticmethod turns the first positional argument into an implicit
        `self`, silently shifting every other argument -- a defect invisible to
        call-site tests that always pass arguments positionally through the class.
        Verified via inspect.getattr_static so the check is independent of how the
        method happens to be invoked.
        """
        import inspect

        static_methods = (
            "process_payment",
            "_process_stripe_payment",
            "_process_razorpay_payment",
            "verify_webhook_signature",
            "_verify_stripe_signature",
            "_verify_razorpay_signature",
            "process_refund",
            "_process_stripe_refund",
            "_process_razorpay_refund",
        )
        for method_name in static_methods:
            with self.subTest(method=method_name):
                descriptor = inspect.getattr_static(PaymentService, method_name)
                self.assertIsInstance(descriptor, staticmethod)

    @override_settings(RAZORPAY_KEY_ID="rzp_test_123", RAZORPAY_KEY_SECRET="secret_123")
    def test_process_razorpay_refund_defaults_reason_notes_when_absent(self):
        """Test the Razorpay refund notes default message is used when no reason is supplied."""
        self.payment.status = "completed"
        self.payment.payment_method = "razorpay"
        self.payment.transaction_id = "pay_test_123"
        self.payment.save(update_fields=["status", "payment_method", "transaction_id"])

        mock_client = MagicMock()
        mock_client.payment.refund.return_value = {"id": "rfnd_default_123"}

        with patch("src.modules.billing_subscriptions.services.razorpay.Client", return_value=mock_client):
            result = PaymentService._process_razorpay_refund(self.payment, None, None)

        self.assertTrue(result["success"])
        mock_client.payment.refund.assert_called_once_with(
            "pay_test_123",
            {
                "amount": 10000,
                "speed": "normal",
                "notes": {"reason": "Customer requested refund"},
            },
        )

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
