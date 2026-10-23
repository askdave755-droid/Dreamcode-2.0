"""Stripe webhooks, the customer payment page, and our own subscription billing."""
import html
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..deps import current_business
from ..plans import PLANS, plan_list
from ..services import billing, messaging, payments

log = logging.getLogger("autopilot.stripe")
router = APIRouter(tags=["payments"])


def _record_event(db: Session, provider: str, external_id: Optional[str]) -> bool:
    """True when this event is new. False on a provider retry."""
    if not external_id:
        return True
    event = models.WebhookEvent(provider=provider, external_id=str(external_id))
    db.add(event)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")
    event = payments.parse_webhook(payload, signature)
    if event is None:
        raise HTTPException(400, "Invalid payload or signature")

    if not _record_event(db, "stripe", event.get("id")):
        return {"received": True, "duplicate": True}

    event_type = event.get("type", "")
    data = (event.get("data") or {}).get("object") or {}

    if event_type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        metadata = data.get("metadata") or {}
        invoice_id = metadata.get("invoice_id")
        if invoice_id:
            invoice = db.get(models.Invoice, invoice_id)
            if invoice is not None and invoice.status != "paid":
                business = db.get(models.Business, invoice.business_id)
                if business:
                    billing.mark_paid(
                        db,
                        business,
                        invoice,
                        via="stripe",
                        amount_cents=data.get("amount_total") or None,
                    )
        else:
            business_id = metadata.get("business_id") or data.get("client_reference_id")
            business = db.get(models.Business, business_id) if business_id else None
            if business:
                business.plan = "pro" if "pro" in str(metadata).lower() else "starter"
                business.plan_status = "active"
                business.paused = False
                business.stripe_customer_id = data.get("customer")
                business.stripe_subscription_id = data.get("subscription")
                db.commit()
                messaging.send_to_owner(
                    db,
                    business,
                    "Subscription active — thanks! Your Autopilot line is live. "
                    "Reply TODAY anytime for your schedule.",
                    template="subscription_active",
                )

    elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")
        if subscription_id or customer_id:
            business = (
                db.query(models.Business)
                .filter(
                    models.Business.stripe_subscription_id == subscription_id
                    if subscription_id
                    else models.Business.stripe_customer_id == customer_id
                )
                .first()
            )
            if business:
                business.plan_status = "active"
                db.commit()

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        business = (
            db.query(models.Business)
            .filter(models.Business.stripe_customer_id == customer_id)
            .first()
        )
        if business:
            business.plan_status = "past_due"
            db.commit()
            messaging.send_to_owner(
                db,
                business,
                "Your Autopilot payment didn't go through. Update your card here: "
                f"{settings.base_url}/billing — your line stays on for now.",
                template="subscription_past_due",
            )

    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        business = (
            db.query(models.Business)
            .filter(models.Business.stripe_subscription_id == data.get("id"))
            .first()
        )
        if business:
            business.plan_status = "canceled"
            business.paused = True
            db.commit()

    return {"received": True}


# ---------------------------------------------------------------------------
# Customer-facing payment page
# ---------------------------------------------------------------------------
PAY_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pay invoice {number}</title>
<style>
:root{{color-scheme:light}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#f4f5f7;color:#16181d;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:20px}}
.card{{background:#fff;border:1px solid #e3e5e9;border-radius:16px;max-width:420px;width:100%;
padding:28px;box-shadow:0 10px 30px rgba(20,25,40,.06)}}
h1{{font-size:18px;margin:0 0 4px}}
.muted{{color:#6b7280;font-size:13px;margin:0 0 18px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-bottom:14px}}
td{{padding:6px 0;color:#374151}}
td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}
.total{{border-top:1px solid #e5e7eb;font-weight:700;font-size:16px;padding-top:10px}}
.paid{{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:12px;border-radius:10px;font-size:14px}}
button{{width:100%;padding:14px;border:0;border-radius:12px;background:#111827;color:#fff;
font-size:16px;font-weight:600;margin-top:16px;cursor:pointer}}
button:active{{transform:translateY(1px)}}
.note{{font-size:12px;color:#6b7280;margin-top:14px;line-height:1.5}}
</style></head><body><div class="card">
<h1>{business_name}</h1>
<p class="muted">Invoice {number}{service}</p>
<table>
<tr><td>Subtotal</td><td>${subtotal}</td></tr>
{tax_rows}
<tr class="total"><td>Total due</td><td>${total}</td></tr>
</table>
{body}
<p class="note">{contact_note}</p>
</div></body></html>"""


def _rate_label(rate: float) -> str:
    """9.975 stays 9.975; 5.0 becomes 5."""
    return f"{rate * 100:.3f}".rstrip("0").rstrip(".")


def _money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


@router.get("/pay/{invoice_id}")
def pay_page(invoice_id: str, db: Session = Depends(get_db)):
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    business = db.get(models.Business, invoice.business_id)
    job = db.get(models.Job, invoice.job_id) if invoice.job_id else None

    if invoice.status == "paid":
        body = '<div class="paid">Paid — thank you! A receipt was texted to you.</div>'
    elif invoice.payment_url and not settings.payments_dry_run:
        body = (
            f'<a href="{html.escape(invoice.payment_url)}">'
            f'<button>Pay {_money(invoice.total_cents)} by card</button></a>'
        )
    else:
        body = (
            f'<form method="post" action="/pay/{invoice.id}/complete">'
            f'<button type="submit">Pay {_money(invoice.total_cents)} (demo)</button></form>'
        )

    tax_rows = "".join(
        f"<tr><td>{html.escape(component.get('label','Tax'))} "
        f"({_rate_label(component.get('rate', 0))}%)</td>"
        f"<td>${_money(component.get('amount_cents', 0))}</td></tr>"
        for component in (invoice.tax_breakdown or [])
    )
    contact = (
        f"Questions? Text {business.phone_number}."
        if business and business.phone_number
        else ""
    )
    if business and business.etransfer_email and invoice.status != "paid":
        contact += f" Prefer e-Transfer? Send to {business.etransfer_email}."

    return Response(
        content=PAY_PAGE.format(
            number=html.escape(invoice.number),
            business_name=html.escape(business.name if business else "Invoice"),
            service=html.escape(f" — {job.service_name}" if job else ""),
            subtotal=_money(invoice.subtotal_cents),
            total=_money(invoice.total_cents),
            tax_rows=tax_rows,
            body=body,
            contact_note=html.escape(contact),
        ),
        media_type="text/html",
    )


@router.post("/pay/{invoice_id}/complete")
def pay_complete(invoice_id: str, db: Session = Depends(get_db)):
    """Demo payment button. Live payments always come through Stripe webhooks."""
    if not settings.payments_dry_run:
        raise HTTPException(404, "Not found")
    invoice = db.get(models.Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    business = db.get(models.Business, invoice.business_id)
    billing.mark_paid(db, business, invoice, via="stripe_demo")
    return Response(
        content=(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h1>Thanks!</h1><p>Payment recorded. A receipt was texted to you.</p>"
            f"<p><a href='/pay/{invoice.id}'>Back to invoice</a></p></body></html>"
        ),
        media_type="text/html",
    )


# ---------------------------------------------------------------------------
# Our subscription billing
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    plan: str = "starter"


@router.get("/api/billing/plans")
def billing_plans():
    return {"plans": plan_list(), "dry_run": settings.payments_dry_run}


@router.post("/api/billing/checkout")
def billing_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    if payload.plan not in PLANS:
        raise HTTPException(400, "Unknown plan")
    plan = PLANS[payload.plan]
    price_id = (
        settings.stripe_subscription_price_id_pro
        if payload.plan == "pro"
        else settings.stripe_subscription_price_id
    )
    if not price_id:
        if settings.payments_dry_run:
            business.plan = payload.plan
            business.plan_status = "active"
            business.minutes_included = plan["minutes_included"]
            business.paused = False
            db.commit()
            return {
                "demo": True,
                "url": None,
                "message": f"Demo mode: plan switched to {plan['name']}.",
            }
        raise HTTPException(500, f"Missing Stripe price for {payload.plan}")

    url, session_id, error = payments.create_subscription_checkout(business, price_id)
    if error or not url:
        raise HTTPException(502, error or "Could not create checkout")
    return {"url": url, "session_id": session_id, "plan": payload.plan}


@router.get("/api/billing/summary")
def billing_summary(
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    calls = (
        db.query(models.Call)
        .filter(models.Call.business_id == business.id)
        .all()
    )
    minutes = sum(call.duration_seconds or 0 for call in calls) // 60
    included = business.minutes_included or 0
    overage = max(minutes - included, 0)
    plan = PLANS.get(business.plan, PLANS["starter"])
    return {
        "plan": business.plan,
        "plan_name": plan["name"],
        "plan_status": business.plan_status,
        "minutes_used": minutes,
        "minutes_included": included,
        "overage_minutes": overage,
        "overage_cents": overage * plan["overage_cents_per_minute"],
        "monthly_cents": plan["price_cents"],
        "trial_ends_at": business.trial_ends_at.isoformat() if business.trial_ends_at else None,
        "dry_run": settings.payments_dry_run,
    }
