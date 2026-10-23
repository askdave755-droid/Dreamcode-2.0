"""Message templates and the one function every feature uses to text someone.

Rules enforced here:
* Owner messages never carry the customer opt-out footer.
* Customer messages always carry the CASL opt-out line unless already present.
* Opted-out customers are skipped for everything except a direct reply to their
  own inbound message (handled in the router), and every attempt is logged.
"""
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..availability import format_local, to_local
from .sms import send_sms


def money(cents: Optional[int]) -> str:
    if cents is None:
        return "$0"
    return f"${cents / 100:,.2f}"


def footer(business: models.Business, body: str) -> str:
    note = business.sms_footer or "Reply STOP to opt out."
    if "stop" in body.lower():
        return body
    return f"{body} {note}".strip()


def record(
    db: Session,
    business: models.Business,
    *,
    direction: str,
    to_number: Optional[str],
    from_number: Optional[str],
    body: str,
    template: Optional[str] = None,
    customer: Optional[models.Customer] = None,
    job: Optional[models.Job] = None,
    invoice: Optional[models.Invoice] = None,
    status: str = "queued",
    provider_sid: Optional[str] = None,
    meta: Optional[dict] = None,
) -> models.Message:
    message = models.Message(
        business_id=business.id,
        customer_id=customer.id if customer else None,
        job_id=job.id if job else None,
        invoice_id=invoice.id if invoice else None,
        direction=direction,
        to_number=to_number,
        from_number=from_number,
        body=body,
        template=template,
        provider_sid=provider_sid,
        status=status,
        meta=meta or {},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def send_to_owner(
    db: Session,
    business: models.Business,
    body: str,
    *,
    template: Optional[str] = None,
    job: Optional[models.Job] = None,
) -> models.Message:
    result = send_sms(business.owner_phone, body, business.phone_number)
    return record(
        db,
        business,
        direction="out",
        to_number=business.owner_phone,
        from_number=business.phone_number,
        body=body,
        template=template,
        job=job,
        status=result.status,
        provider_sid=result.sid,
    )


def send_to_customer(
    db: Session,
    business: models.Business,
    customer: models.Customer,
    body: str,
    *,
    template: Optional[str] = None,
    job: Optional[models.Job] = None,
    invoice: Optional[models.Invoice] = None,
    allow_opt_out: bool = False,
) -> Optional[models.Message]:
    """Send a customer text, respecting opt-out and CASL footer."""
    if customer.sms_opt_out_at and not allow_opt_out:
        record(
            db,
            business,
            direction="out",
            to_number=customer.phone,
            from_number=business.phone_number,
            body=body,
            template=template,
            customer=customer,
            job=job,
            invoice=invoice,
            status="skipped_opt_out",
        )
        return None

    payload = footer(business, body)
    result = send_sms(customer.phone, payload, business.phone_number)
    return record(
        db,
        business,
        direction="out",
        to_number=customer.phone,
        from_number=business.phone_number,
        body=payload,
        template=template,
        customer=customer,
        job=job,
        invoice=invoice,
        status=result.status,
        provider_sid=result.sid,
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def tpl_job_booked_owner(business: models.Business, job: models.Job) -> str:
    customer = job.customer
    when = format_local(job.scheduled_start, business) if job.scheduled_start else (
        job.requested_for or "time TBD"
    )
    return (
        f"NEW JOB #{job.number}: {job.service_name} for "
        f"{customer.name if customer else 'caller'} at {job.address or 'address TBD'}"
        f" — {when}. Reply DONE {job.number} when finished, TODAY for your list."
    )


def tpl_customer_confirmation(business: models.Business, job: models.Job) -> str:
    when = format_local(job.scheduled_start, business) if job.scheduled_start else (
        job.requested_for or "a time to be confirmed"
    )
    if job.status == "needs_confirmation":
        return (
            f"{business.name}: thanks for the request — we have you down for "
            f"{job.service_name}, {when}. We'll text to confirm the exact time shortly."
        )
    return (
        f"{business.name}: you're booked for {job.service_name} on {when}. "
        f"We'll send a reminder the day before. Reply R to reschedule."
    )


def tpl_reminder(business: models.Business, job: models.Job) -> str:
    local = to_local(job.scheduled_start, business)
    when = local.strftime("%-I:%M %p") if local else "soon"
    return (
        f"Reminder from {business.name}: {job.service_name} is scheduled for "
        f"tomorrow at {when}. Reply C to confirm or R to reschedule."
    )


def tpl_invoice(business: models.Business, invoice: models.Invoice, job: Optional[models.Job]) -> str:
    service = job.service_name if job else "your recent service"
    parts = [
        f"{business.name}: invoice {invoice.number} for {service} — "
        f"{money(invoice.total_cents)} incl. tax."
    ]
    if invoice.payment_url:
        parts.append(f"Pay by card: {invoice.payment_url}")
    if invoice.method == "etransfer" and invoice.etransfer_email:
        parts.append(f"Or Interac e-Transfer to {invoice.etransfer_email}")
    elif invoice.method == "cash":
        parts.append("Payment is due on completion — cash or cheque.")
    elif invoice.method == "etransfer":
        parts.append("Reply and we'll send e-Transfer details.")
    return " ".join(parts)


def tpl_payment_reminder(
    business: models.Business, invoice: models.Invoice, job: Optional[models.Job]
) -> str:
    service = job.service_name if job else "your service"
    text = (
        f"Friendly reminder from {business.name}: invoice {invoice.number} "
        f"({money(invoice.total_cents)} for {service}) is still open."
    )
    if invoice.payment_url:
        text += f" Pay here: {invoice.payment_url}"
    if invoice.method == "etransfer" and invoice.etransfer_email:
        text += f" Or e-Transfer to {invoice.etransfer_email}"
    text += " Already paid? Reply PAID."
    return text


def tpl_paid(business: models.Business, invoice: models.Invoice) -> str:
    return (
        f"Thank you! {business.name} received {money(invoice.total_cents)} "
        f"for invoice {invoice.number}. Your receipt is on file."
    )


def tpl_review(business: models.Business, customer: models.Customer) -> str:
    name = (customer.name or "").split(" ")[0]
    greeting = f"Thanks for choosing {business.name}, {name}!" if name else (
        f"Thanks for choosing {business.name}!"
    )
    return (
        f"{greeting} If we earned it, a quick Google review helps our small business "
        f"a lot: {business.review_url}"
    )


def tpl_rebook(business: models.Business, job: models.Job, customer: models.Customer) -> str:
    name = (customer.name or "").split(" ")[0]
    opener = f"Hi {name}, {business.name} here." if name else f"Hi, {business.name} here."
    return (
        f"{opener} It's time to book your {job.service_name.lower()} again. "
        f"Reply BOOK and we'll find a slot."
    )


def tpl_owner_escalation(
    business: models.Business,
    *,
    summary: str,
    caller_name: Optional[str],
    caller_phone: Optional[str],
    urgency: str = "normal",
) -> str:
    who = caller_name or "a caller"
    contact = f" ({caller_phone})" if caller_phone else ""
    if urgency == "emergency":
        return f"URGENT — {who}{contact}: {summary}"
    return f"Callback needed — {who}{contact}: {summary}"


def tpl_owner_job_confirmed(business: models.Business, job: models.Job) -> str:
    return (
        f"Job #{job.number} confirmed: {job.service_name} for "
        f"{(job.customer.name if job.customer else 'customer')} — "
        f"{format_local(job.scheduled_start, business)}."
    )
