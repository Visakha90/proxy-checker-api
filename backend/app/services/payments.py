"""
Stripe Payment Integration for premium subscriptions.

Supports:
- Creating checkout sessions for plan upgrades
- Handling webhook events (subscription created/cancelled)
- Managing customer billing portal
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.database import async_session
from app.core.config import get_settings
from app.models.user_models import User

logger = logging.getLogger(__name__)
settings = get_settings()

# Stripe config from environment
STRIPE_SECRET_KEY = getattr(settings, "stripe_secret_key", "")
STRIPE_WEBHOOK_SECRET = getattr(settings, "stripe_webhook_secret", "")
STRIPE_PRICE_PRO = getattr(settings, "stripe_price_pro", "price_pro_monthly")
STRIPE_PRICE_ENTERPRISE = getattr(settings, "stripe_price_enterprise", "price_enterprise_monthly")

PLAN_PRICES = {
    "pro": STRIPE_PRICE_PRO,
    "enterprise": STRIPE_PRICE_ENTERPRISE,
}


class PaymentService:
    """Manages Stripe subscriptions and billing."""

    def _get_stripe(self):
        """Lazy import stripe to avoid errors when not installed."""
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            return stripe
        except ImportError:
            logger.warning("Stripe package not installed. Payment features disabled.")
            return None

    async def create_checkout_session(
        self, user_id: int, plan: str, success_url: str, cancel_url: str
    ) -> dict:
        """Create a Stripe checkout session for subscription."""
        stripe = self._get_stripe()
        if not stripe or not STRIPE_SECRET_KEY:
            return {"error": "Payments not configured. Set STRIPE_SECRET_KEY."}

        if plan not in PLAN_PRICES:
            return {"error": f"Invalid plan. Available: {', '.join(PLAN_PRICES.keys())}"}

        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return {"error": "User not found"}

        # Create or retrieve Stripe customer
        customer_id = user.stripe_customer_id
        if not customer_id:
            customer = stripe.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
            customer_id = customer.id
            async with async_session() as session:
                await session.execute(
                    update(User).where(User.id == user.id).values(stripe_customer_id=customer_id)
                )
                await session.commit()

        # Create checkout session
        checkout = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": PLAN_PRICES[plan], "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id), "plan": plan},
        )

        return {"checkout_url": checkout.url, "session_id": checkout.id}

    async def handle_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Handle Stripe webhook events."""
        stripe = self._get_stripe()
        if not stripe:
            return {"error": "Stripe not configured"}

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            return {"error": f"Invalid webhook: {e}"}

        event_type = event["type"]
        data = event["data"]["object"]

        if event_type == "checkout.session.completed":
            user_id = int(data["metadata"].get("user_id", 0))
            plan = data["metadata"].get("plan", "pro")
            subscription_id = data.get("subscription")

            if user_id:
                async with async_session() as session:
                    await session.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(
                            plan=plan,
                            role="premium" if plan == "pro" else "admin",
                            stripe_subscription_id=subscription_id,
                        )
                    )
                    await session.commit()
                logger.info(f"User {user_id} upgraded to {plan}")

        elif event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            async with async_session() as session:
                user = await session.scalar(
                    select(User).where(User.stripe_customer_id == customer_id)
                )
                if user:
                    await session.execute(
                        update(User)
                        .where(User.id == user.id)
                        .values(plan="free", role="user", stripe_subscription_id=None)
                    )
                    await session.commit()
                    logger.info(f"User {user.id} subscription cancelled")

        return {"received": True, "type": event_type}

    async def create_portal_session(self, user_id: int, return_url: str) -> dict:
        """Create a Stripe billing portal session."""
        stripe = self._get_stripe()
        if not stripe or not STRIPE_SECRET_KEY:
            return {"error": "Payments not configured"}

        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user or not user.stripe_customer_id:
                return {"error": "No billing account found"}

        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
        )

        return {"portal_url": portal.url}

    async def get_subscription_status(self, user_id: int) -> dict:
        """Get current subscription status."""
        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return {"error": "User not found"}

        return {
            "plan": user.plan,
            "has_subscription": user.stripe_subscription_id is not None,
            "stripe_customer_id": user.stripe_customer_id,
        }


payment_service = PaymentService()
