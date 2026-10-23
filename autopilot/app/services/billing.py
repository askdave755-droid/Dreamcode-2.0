"""Invoicing and the money side of the workflow.

One entry point creates an invoice from a finished job: it applies the
business's tax profile, builds the payment link (or e-Transfer instructions),
texts the customer, and schedules the review + rebooking texts.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..availability import format_local
from ..tax import compute_tax
from . import messaging, payments


def next_sequence(db: Session, business: models.Business, model, field: str = "number") -> int:
    current = (
        db.query(func.max(getattr(model, field)))
        .filter(model.business_id == business.id)
        .scalar()
    )
    return int(current or 0) + 1


def next_job_number(db: Session, business: models.Business) -> int:
    return next_sequence(db, business, models.Job)


def next_invoice_number(db: Session, business: models.Business) -> str:
    count = (
        db.query(func.count(models.Invoice.id))
        .filter(models.Invoice.business_id == business.id)
        .scalar()
        or 0
    )
    return f"INV-{int(count) + 1001}"


def build_invoice(
    db: Session,
    business: models.Business,
    job: models.Job,
    *,
    amount_cents: Optional[int] = None,
    method: Optional[str] = None,
    notes: Optional[str] = None,
) -> models.Invoice:
    """Create (but do not send) an invoice for a completed job."""
    subtotal = amount_cents
    if subtotal is None:
        subtotal = job.price_final_cents or job.price_estimate_low_cents or 0
    chosen_method = method or ("etransfer" if business.etransfer_email else "stripe")
    # An e-Transfer invoice without a destination is undeliverable.
    if chosen_method == "etransfer" and not business.etransfer_email:
        chosen_method = "stripe"

    tax = compute_tax(
        subtotal,
        tax_profile=business.tax_profile if business.hst_enabled else "none",
        enabled=business.hst_enabled,
    )
    invoice = models.Invoice(
        business_id=business.id,
        job_id=job.id,
        customer_id=job.customer_id,
        number=next_invoice_number(db, business),
        status="draft",
        method=chosen_method,
        subtotal_cents=tax.subtotal_cents,
        tax_cents=tax.tax_cents,
        total_cents=tax.total_cents,
        tax_breakdown=tax.breakdown,
        line_items=[
            {
                "description": job.service_name,
                "amount_cents": tax.subtotal_cents,
                "quantity": 1,
            }
        ],
        notes=notes,
        etransfer_email=business.etransfer_email if chosen_method == "etransfer" else None,
        due_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def issue_invoice(
    db: Session, business: models.Business, invoice: models.Invoice
) -> models.Invoice:
    """Attach a payment link (if card) and mark the invoice as sent."""
    if invoice.method == "stripe" and not invoice.payment_url:
        url, session_id, error = payments.create_payment_link(
            invoice, currency=business.currency
        )
        invoice.payment_url = url
        invoice.stripe_session_id = session_id
        if error:
            invoice.notes = (invoice.notes or "") + f"\nStripe error: {error}"

    invoice.status = "sent"
    invoice.issued_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)

    customer = db.get(models.Customer, invoice.customer_id) if invoice.customer_id else None
    job = db.get(models.Job, invoice.job_id) if invoice.job_id else None
    if customer:
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_invoice(business, invoice, job),
            template="invoice",
            job=job,
            invoice=invoice,
        )
    return invoice


def mark_paid(
    db: Session,
    business: models.Business,
    invoice: models.Invoice,
    *,
    via: str = "stripe",
    amount_cents: Optional[int] = None,
) -> models.Invoice:
    """Idempotent: paying twice cannot duplicate the receipt or follow-ups."""
    if invoice.status == "paid":
        return invoice

    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.paid_via = via
    if amount_cents:
        invoice.total_cents = amount_cents

    job = db.get(models.Job, invoice.job_id) if invoice.job_id else None
    if job:
        job.status = "paid"
        job.completed_at = job.completed_at or datetime.now(timezone.utc)
        service = next(
            (s for s in (business.services or []) if s.get("key") == job.service_key), {}
        )
        rebook_days = int(service.get("rebook_after_days") or 0)
        if business.rebook_enabled and rebook_days:
            job.rebook_due_at = datetime.now(timezone.utc) + timedelta(days=rebook_days)
    db.commit()
    db.refresh(invoice)

    customer = db.get(models.Customer, invoice.customer_id) if invoice.customer_id else None
    if customer:
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_paid(business, invoice),
            template="paid_receipt",
            job=job,
            invoice=invoice,
        )
        messaging.send_to_owner(
            db,
            business,
            f"PAID: invoice {invoice.number} — {messaging.money(invoice.total_cents)} "
            f"from {customer.name or customer.phone} ({via}).",
            template="paid_owner",
            job=job,
        )
    return invoice


def tax_summary(business: models.Business, invoices: list[models.Invoice]) -> dict:
    """Quick totals for the dashboard / remittance."""
    paid = [i for i in invoices if i.status == "paid"]
    gst = sum(
        sum(c["amount_cents"] for c in (i.tax_breakdown or []) if c.get("label") == "GST")
        for i in paid
    )
    qst = sum(
        sum(c["amount_cents"] for c in (i.tax_breakdown or []) if c.get("label") == "QST")
        for i in paid
    )
    hst = sum(
        sum(c["amount_cents"] for c in (i.tax_breakdown or []) if c.get("label") == "HST")
        for i in paid
    )
    return {
        "revenue_cents": sum(i.total_cents for i in paid),
        "subtotal_cents": sum(i.subtotal_cents for i in paid),
        "gst_cents": gst,
        "qst_cents": qst,
        "hst_cents": hst,
        "outstanding_cents": sum(
            i.total_cents for i in invoices if i.status in ("sent", "overdue")
        ),
        "paid_count": len(paid),
    }


def job_when(business: models.Business, job: models.Job) -> str:
    return format_local(job.scheduled_start, business)
