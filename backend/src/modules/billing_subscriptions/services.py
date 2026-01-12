"""
BillingSubscriptions Services.

High-level service layer for BillingSubscriptions business logic.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal
from datetime import date, timedelta
from typing import Any, Dict, Optional

import razorpay
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Invoice, Payment, Subscription, SubscriptionPlan

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Service for managing subscriptions and billing."""

    def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        payment_method_id: Optional[str] = None,
    ) -> Subscription:
        """Create a new subscription.

        Args:
            tenant_id: Tenant ID.
            plan_id: Subscription plan ID.
            payment_method_id: Optional payment method ID.

        Returns:
            Created Subscription instance.

        Raises:
            ValueError: If plan not found or validation fails.
        """
        plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
        if not plan:
            raise ValueError(f"Subscription plan {plan_id} not found or inactive")

        with transaction.atomic():
            today = timezone.now().date()
            trial_end = today + timedelta(days=14) if plan.billing_cycle == "monthly" else None

            subscription = Subscription.objects.create(
                tenant_id=tenant_id,
                plan=plan,
                status="trial" if trial_end else "active",
                start_date=today,
                trial_start_date=today if trial_end else None,
                trial_end_date=trial_end,
            )

            # Update tenant quotas
            self._update_tenant_quotas(tenant_id, plan)

            logger.info(f"Created subscription {subscription.id} for tenant {tenant_id}")
            return subscription

    def upgrade_subscription(
        self,
        tenant_id: str,
        new_plan_id: str,
    ) -> Subscription:
        """Upgrade subscription to a new plan.

        Args:
            tenant_id: Tenant ID.
            new_plan_id: New subscription plan ID.

        Returns:
            Updated Subscription instance.

        Raises:
            ValueError: If subscription or plan not found.
        """
        subscription = Subscription.objects.filter(
            tenant_id=tenant_id,
            status__in=["active", "trial"],
        ).first()

        if not subscription:
            raise ValueError(f"No active subscription found for tenant {tenant_id}")

        new_plan = SubscriptionPlan.objects.filter(id=new_plan_id, is_active=True).first()
        if not new_plan:
            raise ValueError(f"Subscription plan {new_plan_id} not found or inactive")

        with transaction.atomic():
            # Calculate proration
            proration_amount = self._calculate_proration(subscription, new_plan)

            # Update subscription
            subscription.plan = new_plan
            if subscription.status == "trial":
                subscription.status = "active"
            subscription.save()

            # Update tenant quotas
            self._update_tenant_quotas(tenant_id, new_plan)

            logger.info(f"Upgraded subscription {subscription.id} to plan {new_plan_id}")
            return subscription

    def cancel_subscription(
        self,
        tenant_id: str,
        reason: str = "",
    ) -> Subscription:
        """Cancel subscription.

        Args:
            tenant_id: Tenant ID.
            reason: Cancellation reason.

        Returns:
            Updated Subscription instance.

        Raises:
            ValueError: If subscription not found.
        """
        subscription = Subscription.objects.filter(
            tenant_id=tenant_id,
            status__in=["active", "trial"],
        ).first()

        if not subscription:
            raise ValueError(f"No active subscription found for tenant {tenant_id}")

        with transaction.atomic():
            subscription.status = "cancelled"
            subscription.cancelled_at = timezone.now()
            subscription.cancellation_reason = reason
            subscription.save()

            logger.info(f"Cancelled subscription {subscription.id} for tenant {tenant_id}")
            return subscription

    def _calculate_proration(
        self,
        subscription: Subscription,
        new_plan: SubscriptionPlan,
    ) -> Decimal:
        """Calculate prorated amount for plan upgrade.

        Args:
            subscription: Current subscription.
            new_plan: New subscription plan.

        Returns:
            Prorated amount.
        """
        # Simple proration: calculate days remaining in current billing cycle
        if subscription.end_date:
            days_remaining = (subscription.end_date - timezone.now().date()).days
            days_in_cycle = (subscription.end_date - subscription.start_date).days
            if days_in_cycle > 0:
                proration_ratio = Decimal(days_remaining) / Decimal(days_in_cycle)
                return new_plan.price * proration_ratio
        return Decimal("0.00")

    def _update_tenant_quotas(
        self,
        tenant_id: str,
        plan: SubscriptionPlan,
    ) -> None:
        """Update tenant resource quotas based on plan limits.

        Args:
            tenant_id: Tenant ID.
            plan: Subscription plan.
        """
        from src.modules.tenant_management.models import Tenant

        try:
            tenant = Tenant.objects.get(id=tenant_id)

            # Get limits from plan
            limits = plan.limits or {}

            # Update resource limits
            if "max_users" in limits:
                tenant.max_users = limits["max_users"]
            if "max_storage_gb" in limits:
                tenant.max_storage_gb = limits["max_storage_gb"]
            if "max_api_calls_per_day" in limits:
                tenant.max_api_calls_per_day = limits["max_api_calls_per_day"]

            # Update subscription plan reference
            tenant.subscription_plan_id = plan.id

            tenant.save(update_fields=["max_users", "max_storage_gb", "max_api_calls_per_day", "subscription_plan_id"])

            logger.info(f"Updated quotas for tenant {tenant_id} based on plan {plan.name}")

        except Tenant.DoesNotExist:
            logger.error(f"Tenant {tenant_id} not found for quota update")
        except Exception as e:
            logger.error(f"Failed to update tenant quotas: {e}")


class PaymentService:
    """Service for processing payments through multiple gateways."""

    @staticmethod
    def process_payment(
        payment: Payment,
        gateway: str = "stripe",
        payment_method_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process payment through specified gateway.

        Args:
            payment: Payment instance.
            gateway: Payment gateway ('stripe' or 'razorpay').
            payment_method_id: Payment method ID (token, card ID, etc.).

        Returns:
            Dictionary with 'success', 'transaction_id', and optional 'error'.

        Raises:
            ValueError: If gateway is unsupported or payment is invalid.
        """
        if gateway == "stripe":
            return PaymentService._process_stripe_payment(payment, payment_method_id)
        elif gateway == "razorpay":
            return PaymentService._process_razorpay_payment(payment, payment_method_id)
        else:
            raise ValueError(f"Unsupported payment gateway: {gateway}")

    @staticmethod
    def _process_stripe_payment(payment: Payment, payment_method_id: Optional[str]) -> Dict[str, Any]:
        """Process payment through Stripe.

        Args:
            payment: Payment instance.
            payment_method_id: Stripe payment method ID or token.

        Returns:
            Dictionary with processing result.
        """
        try:
            # Initialize Stripe
            stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", None)
            if not stripe.api_key:
                return {"success": False, "error": "Stripe secret key not configured"}

            invoice = payment.invoice
            amount_cents = int(float(payment.amount) * 100)  # Convert to cents

            # Get currency (default to USD if not specified)
            currency = getattr(invoice, "currency", "USD") or "USD"

            # Create payment intent
            payment_intent_data = {
                "amount": amount_cents,
                "currency": currency.lower(),
                "description": f"Invoice {invoice.invoice_number}",
                "metadata": {
                    "invoice_id": str(invoice.id),
                    "payment_id": str(payment.id),
                    "tenant_id": str(payment.tenant_id),
                },
            }

            # Add payment method if provided
            if payment_method_id:
                payment_intent_data["payment_method"] = payment_method_id
                payment_intent_data["confirmation_method"] = "manual"
                payment_intent_data["confirm"] = True

            # Create payment intent
            intent = stripe.PaymentIntent.create(**payment_intent_data)

            # Update payment record
            payment.transaction_id = intent.id
            payment.payment_method = "stripe"

            if intent.status == "succeeded":
                payment.status = "completed"
                payment.processed_at = timezone.now()
                payment.save(update_fields=["status", "transaction_id", "processed_at", "payment_method"])

                # Update invoice status
                invoice.status = "paid"
                invoice.paid_at = payment.processed_at
                invoice.save(update_fields=["status", "paid_at"])

                logger.info(f"Stripe payment succeeded: {intent.id} for payment {payment.id}")
                return {
                    "success": True,
                    "transaction_id": intent.id,
                    "client_secret": intent.client_secret if hasattr(intent, "client_secret") else None,
                }
            elif intent.status == "requires_action":
                # 3D Secure or other authentication required
                payment.save(update_fields=["transaction_id", "payment_method"])
                return {
                    "success": False,
                    "requires_action": True,
                    "client_secret": intent.client_secret,
                    "transaction_id": intent.id,
                }
            else:
                payment.status = "failed"
                payment.save(update_fields=["status", "transaction_id", "payment_method"])
                return {
                    "success": False,
                    "error": f"Payment intent status: {intent.status}",
                    "transaction_id": intent.id,
                }

        except stripe.error.CardError as e:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            logger.error(f"Stripe card error: {e}")
            return {"success": False, "error": f"Card error: {e.user_message}"}
        except stripe.error.StripeError as e:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            logger.error(f"Stripe error: {e}")
            return {"success": False, "error": f"Stripe error: {str(e)}"}
        except Exception as e:
            logger.error(f"Stripe payment processing failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _process_razorpay_payment(payment: Payment, payment_method_id: Optional[str]) -> Dict[str, Any]:
        """Process payment through Razorpay.

        Args:
            payment: Payment instance.
            payment_method_id: Razorpay payment method ID or token.

        Returns:
            Dictionary with processing result.
        """
        try:
            # Initialize Razorpay
            razorpay_key_id = getattr(settings, "RAZORPAY_KEY_ID", None)
            razorpay_key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", None)

            if not razorpay_key_id or not razorpay_key_secret:
                return {"success": False, "error": "Razorpay credentials not configured"}

            client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

            invoice = payment.invoice
            amount_paise = int(float(payment.amount) * 100)  # Convert to paise

            # Get currency (default to USD if not specified)
            currency = getattr(invoice, "currency", "USD") or "USD"

            # Create order
            order_data = {
                "amount": amount_paise,
                "currency": currency.upper(),
                "receipt": f"invoice_{invoice.invoice_number}",
                "notes": {
                    "invoice_id": str(invoice.id),
                    "payment_id": str(payment.id),
                    "tenant_id": str(payment.tenant_id),
                },
            }

            order = client.order.create(data=order_data)

            # Update payment record
            payment.transaction_id = order["id"]
            payment.payment_method = "razorpay"
            payment.save(update_fields=["transaction_id", "payment_method"])

            # If payment_method_id provided, capture payment
            if payment_method_id:
                try:
                    # Capture payment
                    capture_data = {
                        "amount": amount_paise,
                        "currency": currency.upper(),
                    }
                    payment_capture = client.payment.capture(payment_method_id, capture_data)

                    if payment_capture.get("status") == "captured":
                        payment.status = "completed"
                        payment.processed_at = timezone.now()
                        payment.save(update_fields=["status", "processed_at"])

                        # Update invoice status
                        invoice.status = "paid"
                        invoice.paid_at = payment.processed_at
                        invoice.save(update_fields=["status", "paid_at"])

                        logger.info(f"Razorpay payment captured: {payment_method_id} for payment {payment.id}")
                        return {
                            "success": True,
                            "transaction_id": payment_method_id,
                            "order_id": order["id"],
                        }
                    else:
                        payment.status = "failed"
                        payment.save(update_fields=["status"])
                        return {
                            "success": False,
                            "error": f"Payment capture status: {payment_capture.get('status')}",
                            "order_id": order["id"],
                        }

                except razorpay.errors.BadRequestError as e:
                    payment.status = "failed"
                    payment.save(update_fields=["status"])
                    logger.error(f"Razorpay capture error: {e}")
                    return {"success": False, "error": f"Payment capture failed: {str(e)}", "order_id": order["id"]}

            # Return order ID for frontend to complete payment
            return {
                "success": True,
                "order_id": order["id"],
                "transaction_id": order["id"],
                "requires_action": True,  # Frontend needs to complete payment
            }

        except razorpay.errors.BadRequestError as e:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            logger.error(f"Razorpay error: {e}")
            return {"success": False, "error": f"Razorpay error: {str(e)}"}
        except Exception as e:
            logger.error(f"Razorpay payment processing failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_webhook_signature(
        payload: bytes, signature: str, gateway: str = "stripe"
    ) -> bool:
        """Verify webhook signature from payment gateway.

        Args:
            payload: Raw webhook payload.
            signature: Webhook signature header.
            gateway: Payment gateway ('stripe' or 'razorpay').

        Returns:
            True if signature is valid, False otherwise.
        """
        if gateway == "stripe":
            return PaymentService._verify_stripe_signature(payload, signature)
        elif gateway == "razorpay":
            return PaymentService._verify_razorpay_signature(payload, signature)
        else:
            logger.warning(f"Unknown gateway for signature verification: {gateway}")
            return False

    @staticmethod
    def _verify_stripe_signature(payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature."""
        try:
            webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
            if not webhook_secret:
                logger.warning("Stripe webhook secret not configured")
                return False

            stripe.Webhook.construct_event(payload, signature, webhook_secret)
            return True
        except ValueError:
            return False
        except stripe.error.SignatureVerificationError:
            return False

    @staticmethod
    def _verify_razorpay_signature(payload: bytes, signature: str) -> bool:
        """Verify Razorpay webhook signature."""
        try:
            webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", None)
            if not webhook_secret:
                logger.warning("Razorpay webhook secret not configured")
                return False

            # Razorpay uses HMAC SHA256
            expected_signature = hmac.new(
                webhook_secret.encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected_signature, signature)
        except Exception:
            return False

    @staticmethod
    def process_refund(
        payment: Payment, amount: Optional[Decimal] = None, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process refund for a payment.

        Args:
            payment: Payment instance.
            amount: Refund amount (default: full amount).
            reason: Refund reason.

        Returns:
            Dictionary with refund result.
        """
        if payment.status != "completed":
            return {"success": False, "error": "Payment must be completed to refund"}

        if payment.payment_method == "stripe":
            return PaymentService._process_stripe_refund(payment, amount, reason)
        elif payment.payment_method == "razorpay":
            return PaymentService._process_razorpay_refund(payment, amount, reason)
        else:
            return {"success": False, "error": f"Unsupported payment method: {payment.payment_method}"}

    @staticmethod
    def _process_stripe_refund(
        payment: Payment, amount: Optional[Decimal], reason: Optional[str]
    ) -> Dict[str, Any]:
        """Process Stripe refund."""
        try:
            stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", None)
            if not stripe.api_key:
                return {"success": False, "error": "Stripe secret key not configured"}

            refund_amount = int(float(amount or payment.amount) * 100)  # Convert to cents

            refund = stripe.Refund.create(
                payment_intent=payment.transaction_id,
                amount=refund_amount,
                reason=reason or "requested_by_customer",
            )

            payment.status = "refunded"
            payment.save(update_fields=["status"])

            logger.info(f"Stripe refund processed: {refund.id} for payment {payment.id}")
            return {"success": True, "refund_id": refund.id}

        except stripe.error.StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _process_razorpay_refund(
        payment: Payment, amount: Optional[Decimal], reason: Optional[str]
    ) -> Dict[str, Any]:
        """Process Razorpay refund."""
        try:
            razorpay_key_id = getattr(settings, "RAZORPAY_KEY_ID", None)
            razorpay_key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", None)

            if not razorpay_key_id or not razorpay_key_secret:
                return {"success": False, "error": "Razorpay credentials not configured"}

            client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

            refund_amount = int(float(amount or payment.amount) * 100)  # Convert to paise

            refund_data = {
                "amount": refund_amount,
                "speed": "normal",  # or 'optimum'
                "notes": {"reason": reason or "Customer requested refund"},
            }

            refund = client.payment.refund(payment.transaction_id, refund_data)

            payment.status = "refunded"
            payment.save(update_fields=["status"])

            logger.info(f"Razorpay refund processed: {refund['id']} for payment {payment.id}")
            return {"success": True, "refund_id": refund["id"]}

        except razorpay.errors.BadRequestError as e:
            logger.error(f"Razorpay refund error: {e}")
            return {"success": False, "error": str(e)}
