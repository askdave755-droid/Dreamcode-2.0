"""Text-message commands — the owner interface that ships before any dashboard.

Owners text the business line; the app recognizes their number and replies with
one short line of confirmation plus an instruction. Customers text back simple
keywords (C / R / BOOK / PAID / STOP).
"""
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..availability import format_local, next_open_days
from ..tax import compute_tax
from ..phoneutil import format_phone, normalize_phone
from . import billing, jobs, messaging

HELP_TEXT = (
    "Commands: TODAY (schedule), DONE <#job> [amount] (invoice it), "
    "PAID <#invoice> (e-transfer received), CONFIRM <#job> <time>, "
    "RESCHEDULE <#job> <time>, CANCEL <#job>, OPEN (availability), "
    "QUOTE <#job> <amount>, PLAN (billing), HELP."
)

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel all", "arret", "arrêt", "desabonner", "désabonner"}


def parse_amount(text: Optional[str]) -> Optional[int]:
    """'$1,250.50' -> 125050 cents."""
    if not text:
        return None
    match = re.search(r"(\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?)", text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return None


def latest_job(db: Session, business: models.Business, customer_id: Optional[str] = None):
    query = db.query(models.Job).filter(models.Job.business_id == business.id)
    if customer_id:
        query = query.filter(models.Job.customer_id == customer_id)
    return query.order_by(models.Job.created_at.desc()).first()


def latest_open_invoice(db: Session, business: models.Business, customer_id: Optional[str] = None):
    query = db.query(models.Invoice).filter(
        models.Invoice.business_id == business.id,
        models.Invoice.status.in_(("sent", "overdue")),
    )
    if customer_id:
        query = query.filter(models.Invoice.customer_id == customer_id)
    return query.order_by(models.Invoice.created_at.desc()).first()


# ---------------------------------------------------------------------------
# Owner commands
# ---------------------------------------------------------------------------
def handle_owner_message(db: Session, business: models.Business, body: str) -> str:
    text = body.strip()
    upper = text.upper()
    words = upper.split()
    verb = words[0] if words else ""

    if verb in ("HELP", "?", "COMMANDS"):
        return HELP_TEXT

    if verb in ("TODAY", "AGENDA", "SCHEDULE"):
        return agenda_text(db, business)

    if verb == "OPEN":
        return availability_text(db, business)

    if verb == "PLAN":
        return (
            f"Current plan: {business.plan} ({business.plan_status}). "
            f"Starter $79/mo includes 200 voice minutes; Pro $149/mo includes 600. "
            f"Reply UPGRADE or visit {_billing_url()}."
        )

    if verb == "UPGRADE":
        return f"Manage your plan here: {_billing_url()}"

    if verb == "DONE":
        job_ref = words[1] if len(words) > 1 else None
        amount = parse_amount(text.replace(verb, "", 1).replace(job_ref or "", "", 1))
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None:
            return "I couldn't find that job. Text TODAY to see open jobs."
        if job.status == "paid":
            return f"Job #{job.number} is already paid. Nothing to do."
        invoice = jobs.complete_job(db, business, job, amount_cents=amount)
        note = "" if amount else " (estimate used — text QUOTE 3 145 to fix)"
        return (
            f"Invoice {invoice.number} sent for {messaging.money(invoice.total_cents)} "
            f"to {job.customer.name if job.customer else 'the customer'}{note}."
        )

    if verb == "QUOTE":
        job_ref = words[1] if len(words) > 1 else None
        amount = parse_amount(text.replace(verb, "", 1).replace(job_ref or "", "", 1))
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None:
            return "Which job? Use: QUOTE <job#> <amount>."
        if not amount:
            return "Send it like: QUOTE 3 145 (or 145.50)."
        job.price_final_cents = amount
        db.commit()
        invoice = (
            db.query(models.Invoice)
            .filter(models.Invoice.business_id == business.id, models.Invoice.job_id == job.id)
            .order_by(models.Invoice.created_at.desc())
            .first()
        )
        if invoice and invoice.status != "paid":
            invoice.subtotal_cents = amount
            tax = compute_tax(
                amount,
                tax_profile=business.tax_profile,
                enabled=business.hst_enabled,
            )
            invoice.tax_cents = tax.tax_cents
            invoice.total_cents = tax.total_cents
            invoice.tax_breakdown = tax.breakdown
            db.commit()
            billing.issue_invoice(db, business, invoice)
            return f"Re-sent invoice {invoice.number} for {messaging.money(invoice.total_cents)}."
        return f"Job #{job.number} priced at {messaging.money(amount)}. Text DONE {job.number} to invoice."

    if verb == "PAID":
        inv_ref = words[1] if len(words) > 1 else None
        invoice = None
        if inv_ref:
            invoice = (
                db.query(models.Invoice)
                .filter(
                    models.Invoice.business_id == business.id,
                    or_(
                        models.Invoice.number == inv_ref,
                        models.Invoice.id == inv_ref,
                    ),
                )
                .first()
            )
        invoice = invoice or latest_open_invoice(db, business)
        if invoice is None:
            return "No open invoice found."
        billing.mark_paid(db, business, invoice, via="etransfer")
        return f"Marked {invoice.number} paid ({messaging.money(invoice.total_cents)}). Receipt sent."

    if verb == "CONFIRM":
        job_ref = words[1] if len(words) > 1 else None
        when = text.split(" ", 2)[2] if len(words) > 2 else None
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None:
            return "Which job? Use: CONFIRM 3 9am"
        try:
            jobs.confirm_job(db, business, job, when)
        except jobs.BookingError as exc:
            return f"Couldn't confirm: {exc.reason.replace('_', ' ')}. Text OPEN for free slots."
        return f"Job #{job.number} confirmed for {format_local(job.scheduled_start, business)}."

    if verb in ("RESCHEDULE", "MOVE"):
        job_ref = words[1] if len(words) > 1 else None
        when = text.split(" ", 2)[2] if len(words) > 2 else None
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None or not when:
            return "Use: RESCHEDULE 3 tomorrow 9am"
        try:
            jobs.confirm_job(db, business, job, when)
        except jobs.BookingError as exc:
            return f"That slot won't work ({exc.reason.replace('_', ' ')}). Text OPEN for options."
        return f"Moved job #{job.number} to {format_local(job.scheduled_start, business)}."

    if verb == "CANCEL":
        job_ref = words[1] if len(words) > 1 else None
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None:
            return "Which job? Use: CANCEL 3"
        jobs.cancel_job(db, business, job, reason="owner cancelled by text")
        return f"Job #{job.number} cancelled. Customer notified."

    if verb in ("WHO",):
        job_ref = words[1] if len(words) > 1 else None
        job = jobs.get_job(db, business, job_ref) if job_ref else latest_job(db, business)
        if job is None or job.customer is None:
            return "No customer on that job."
        customer = job.customer
        return (
            f"#{job.number} {customer.name or 'unnamed'} {format_phone(customer.phone)} "
            f"{customer.address_line1 or job.address or ''}".strip()
        )

    # A bare amount while an open job exists is a common owner shortcut.
    amount = parse_amount(text)
    if amount and len(text) < 14:
        job = latest_job(db, business)
        if job and job.status not in ("paid", "cancelled"):
            job.price_final_cents = amount
            db.commit()
            return f"Job #{job.number} priced at {messaging.money(amount)}. Text DONE {job.number} when finished."

    return f"I didn't catch that. {HELP_TEXT}"


def agenda_text(db: Session, business: models.Business) -> str:
    upcoming = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status.in_(("confirmed", "in_progress")),
            models.Job.scheduled_start.isnot(None),
        )
        .order_by(models.Job.scheduled_start.asc())
        .limit(6)
        .all()
    )
    pending = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status.in_(("requested", "needs_confirmation")),
        )
        .order_by(models.Job.created_at.asc())
        .limit(4)
        .all()
    )
    if not upcoming and not pending:
        return "Nothing on the schedule. Text OPEN to see free slots."

    lines = []
    if upcoming:
        lines.append("Schedule:")
        for job in upcoming:
            local = format_local(job.scheduled_start, business)
            who = job.customer.name if job.customer else "customer"
            lines.append(f"#{job.number} {local} — {job.service_name} — {who}")
    if pending:
        lines.append("Needs your call:")
        for job in pending:
            who = job.customer.name if job.customer else "customer"
            lines.append(f"#{job.number} {job.service_name} — {who} — wants {job.requested_for or 'TBD'}")
    unpaid = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.business_id == business.id,
            models.Invoice.status.in_(("sent", "overdue")),
        )
        .count()
    )
    if unpaid:
        lines.append(f"{unpaid} unpaid invoice(s).")
    return "\n".join(lines)


def availability_text(db: Session, business: models.Business) -> str:
    days = next_open_days(business, jobs.active_jobs(db, business), days_ahead=7, per_day=2)
    if not days:
        return "No open slots in the next 7 days. Check your hours in the dashboard."
    lines = ["Open slots:"]
    for day in days[:4]:
        times = ", ".join(
            datetime.fromisoformat(slot).strftime("%-I:%M %p") for slot in day["slots"]
        )
        lines.append(f"{day['label']}: {times}")
    lines.append("Reply with a time to book, or nothing.")
    return "\n".join(lines)


def _billing_url() -> str:
    from ..config import settings

    return f"{settings.base_url}/billing"


# ---------------------------------------------------------------------------
# Customer replies
# ---------------------------------------------------------------------------
def handle_customer_message(db: Session, business: models.Business, customer: models.Customer, body: str) -> Optional[str]:
    text = body.strip()
    upper = text.upper()
    word = upper.split()[0] if upper.split() else ""

    if upper.lower() in STOP_WORDS or word in ("STOP", "ARRET", "ARRÊT"):
        customer.sms_opt_out_at = datetime.now(timezone.utc)
        customer.sms_consent = False
        db.commit()
        return (
            f"{business.name}: you're unsubscribed and won't get more texts. "
            f"Reply START to opt back in."
        )

    if word in ("START", "UNSTOP"):
        customer.sms_opt_out_at = None
        customer.sms_consent = True
        customer.sms_consent_at = datetime.now(timezone.utc)
        customer.sms_consent_source = "sms_start"
        db.commit()
        return f"{business.name}: you're back on the list. Reply BOOK to schedule."

    job = latest_job(db, business, customer.id)

    if word in ("C", "CONFIRM", "YES", "Y", "OK", "OUI"):
        if job and job.status == "confirmed":
            return f"Thanks — you're confirmed for {format_local(job.scheduled_start, business)}."
        if job and job.scheduled_start is None:
            return (
                f"{business.name}: thanks! We'll text you shortly to lock the exact time."
            )
        return f"{business.name}: nothing to confirm right now. Reply BOOK to schedule."

    if word in ("R", "RESCHEDULE", "MOVE") or upper.startswith("R "):
        if job is None:
            return f"{business.name}: reply BOOK and we'll set something up."
        when = text.split(" ", 1)[1] if " " in text else None
        if not when:
            return (
                f"{business.name}: no problem — what day and time works better? "
                f"(e.g. 'Fri 9am')"
            )
        from ..availability import parse_datetime_loose

        parsed = parse_datetime_loose(when, business)
        if parsed is None:
            return f"{business.name}: I couldn't read that time. Try 'Fri 9am' or 'Nov 12 1pm'."
        job.requested_for = when
        job.notes = f"{job.notes or ''}\nCustomer requested reschedule: {when}".strip()
        db.commit()
        messaging.send_to_owner(
            db,
            business,
            f"RESCHEDULE REQUEST — job #{job.number} "
            f"({job.customer.name if job.customer else 'customer'}): {when}. "
            f"Reply CONFIRM {job.number} {when}.",
            template="reschedule_request",
            job=job,
        )
        return f"{business.name}: got it — we'll confirm {when} shortly."

    if word in ("BOOK", "REBOOK", "AGAIN"):
        if job is None:
            return f"{business.name}: what can we help with? Reply with the service you need."
        messaging.send_to_owner(
            db,
            business,
            f"REBOOK REQUEST — {customer.name or format_phone(customer.phone)} wants "
            f"{job.service_name} again. Call {format_phone(customer.phone)}.",
            template="rebook_request",
        )
        return (
            f"{business.name}: great — we'll text you a time for your next "
            f"{job.service_name.lower()} shortly."
        )

    if word == "PAID":
        invoice = latest_open_invoice(db, business, customer.id)
        if invoice is None:
            return f"{business.name}: we don't have an open invoice for you. Thanks!"
        messaging.send_to_owner(
            db,
            business,
            f"CUSTOMER SAYS PAID — invoice {invoice.number} "
            f"({messaging.money(invoice.total_cents)}, {customer.name or format_phone(customer.phone)}). "
            f"Reply PAID {invoice.number} once you see it.",
            template="customer_claims_paid",
            invoice=invoice,
        )
        return f"{business.name}: thanks — we'll confirm as soon as it lands."

    # Anything else is a human-shaped message: pass it to the owner.
    messaging.send_to_owner(
        db,
        business,
        f"MESSAGE from {customer.name or format_phone(customer.phone)}: {text[:300]} "
        f"(reply directly to them)",
        template="customer_message_relay",
    )
    return f"{business.name}: got it — the owner will get back to you shortly."


def handle_inbound(
    db: Session,
    business: models.Business,
    from_number: str,
    to_number: Optional[str],
    body: str,
) -> str:
    normalized = normalize_phone(from_number) or from_number
    owner_phone = normalize_phone(business.owner_phone)

    if owner_phone and normalized == owner_phone:
        return handle_owner_message(db, business, body)

    customer = (
        db.query(models.Customer)
        .filter(
            models.Customer.business_id == business.id,
            models.Customer.phone == normalized,
        )
        .first()
    )
    if customer is None:
        # Unknown number: create a lead so the conversation is not lost.
        customer = models.Customer(
            business_id=business.id,
            phone=normalized,
            sms_consent=True,
            sms_consent_source="inbound_sms",
            sms_consent_at=datetime.now(timezone.utc),
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        messaging.send_to_owner(
            db,
            business,
            f"NEW TEXT from {format_phone(normalized)}: {body[:300]}",
            template="new_lead_sms",
        )
        return (
            f"{business.name}: thanks for texting! What service do you need and "
            f"what's the address? We'll text back with a time."
        )

    return handle_customer_message(db, business, customer, body) or ""
