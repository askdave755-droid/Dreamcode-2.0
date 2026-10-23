"""Stripe transport: job payment links and the business's own subscription.

When STRIPE_SECRET_KEY is missing the module returns local demo URLs so the
full invoice → payment → review flow can be demonstrated end to end.
"""
import logging
from typing import Optional

import stripe

from ..config import settings

log = logging.getLogger("autopilot.payments")


def _configure() -> bool:
    if settings.payments_dry_run:
        return False
    stripe.api_key = settings.stripe_secret_key
    return True


def create_payment_link(invoice, currency: str = "cad") -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (url, session_id, error) for a Stripe Checkout payment page."""
    if not _configure():
        return (
            f"{settings.base_url}/pay/{invoice.id}",
            f"demo_{invoice.id}",
            None,
        )
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": f"Invoice {invoice.number}",
                            "description": "Service including applicable tax",
                        },
                        "unit_amount": int(invoice.total_cents),
                    },
                    "quantity": 1,
                }
            ],
            metadata={"invoice_id": invoice.id, "business_id": invoice.business_id},
            success_url=f"{settings.base_url}/pay/thanks?invoice={invoice.id}",
            cancel_url=f"{settings.base_url}/pay/{invoice.id}",
        )
        return session.url, session.id, None
    except Exception as exc:  # stripe raises many error types
        log.warning("Stripe checkout failed: %s", exc)
        return None, None, str(exc)


def create_subscription_checkout(business, price_id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not _configure():
        return f"{settings.base_url}/billing/thanks?demo=1", f"demo_sub_{business.id}", None
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=business.owner_email or None,
            client_reference_id=business.id,
            metadata={"business_id": business.id, "kind": "subscription"},
            subscription_data={"metadata": {"business_id": business.id}},
            success_url=f"{settings.base_url}/billing/thanks",
            cancel_url=f"{settings.base_url}/billing",
        )
        return session.url, session.id, None
    except Exception as exc:
        log.warning("Stripe subscription checkout failed: %s", exc)
        return None, None, str(exc)


def parse_webhook(payload: bytes, signature: Optional[str]) -> Optional[dict]:
    """Verify and decode a Stripe webhook. Returns None when unverifiable."""
    if settings.payments_dry_run:
        import json

        try:
            return json.loads(payload.decode() or "{}")
        except Exception:
            return None
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, signature or "", settings.stripe_webhook_secret
            )
            return dict(event)
        except Exception as exc:
            log.warning("Stripe signature rejected: %s", exc)
            return None
    try:
        import json

        return json.loads(payload.decode())
    except Exception:
        return None
