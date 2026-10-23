"""Booking lifecycle. Everything the voice agent, SMS commands, and the
dashboard call lives here so the rules exist in exactly one place.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..availability import (
    format_local,
    parse_datetime_loose,
    slot_is_available,
)
from ..phoneutil import normalize_phone
from . import billing, messaging


class BookingError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(detail or reason)


def active_jobs(db: Session, business: models.Business) -> list[models.Job]:
    return (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status.in_(("requested", "needs_confirmation", "confirmed", "in_progress")),
        )
        .all()
    )


def get_job(db: Session, business: models.Business, job_id_or_number) -> Optional[models.Job]:
    query = db.query(models.Job).filter(models.Job.business_id == business.id)
    if str(job_id_or_number).isdigit():
        return query.filter(models.Job.number == int(job_id_or_number)).first()
    return query.filter(models.Job.id == str(job_id_or_number)).first()


def get_or_create_customer(
    db: Session,
    business: models.Business,
    phone: Optional[str],
    *,
    name: Optional[str] = None,
    address: Optional[str] = None,
    email: Optional[str] = None,
    consent_source: str = "voice_call",
) -> Optional[models.Customer]:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    customer = (
        db.query(models.Customer)
        .filter(
            models.Customer.business_id == business.id,
            models.Customer.phone == normalized,
        )
        .first()
    )
    if customer is None:
        customer = models.Customer(
            business_id=business.id,
            phone=normalized,
            name=name,
            address_line1=address,
            email=email,
            sms_consent=True,
            sms_consent_source=consent_source,
            sms_consent_at=datetime.now(timezone.utc),
        )
        db.add(customer)
        db.flush()
    else:
        if name and not customer.name:
            customer.name = name
        if address and not customer.address_line1:
            customer.address_line1 = address
        if email and not customer.email:
            customer.email = email
    db.commit()
    db.refresh(customer)
    return customer


def resolve_service(business: models.Business, service_key: Optional[str], service_name: Optional[str]):
    services = business.services or []
    if service_key:
        for service in services:
            if service.get("key") == service_key:
                return service
    if service_name:
        needle = service_name.lower()
        for service in services:
            if needle in (service.get("name") or "").lower() or (
                service.get("key") or ""
            ).lower() in needle:
                return service
    return None


def create_job(
    db: Session,
    business: models.Business,
    *,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    address: Optional[str] = None,
    service_key: Optional[str] = None,
    service_name: Optional[str] = None,
    requested_for: Optional[str] = None,
    preferred_start: Optional[str] = None,
    notes: Optional[str] = None,
    source: str = "voice",
    estimate_low_cents: Optional[int] = None,
    estimate_high_cents: Optional[int] = None,
) -> tuple[models.Job, list[str]]:
    """Book a job. Returns (job, warnings).

    A job is only `confirmed` when the requested slot actually passes the
    availability check. Otherwise it is saved as `needs_confirmation` with a
    callback promise — we never tell a caller they are booked when we cannot
    honour the slot.
    """
    warnings: list[str] = []
    customer = get_or_create_customer(
        db,
        business,
        customer_phone,
        name=customer_name,
        address=address,
        consent_source=f"{source}_call" if source == "voice" else source,
    )
    service = resolve_service(business, service_key, service_name)
    if service is None and not service_name:
        raise BookingError("unknown_service", "Tell the caller the owner will confirm the service.")
    if service is None:
        warnings.append("service_not_in_catalogue")

    start: Optional[datetime] = None
    if preferred_start:
        start = parse_datetime_loose(preferred_start, business)
        if start is None:
            warnings.append("could_not_parse_time")
    if start is None and requested_for:
        start = parse_datetime_loose(requested_for, business)

    status = "needs_confirmation"
    window_label = None
    if start is not None:
        ok, reason = slot_is_available(
            business, start, (service or {}).get("key", service_key or ""), active_jobs(db, business)
        )
        if ok:
            status = "confirmed"
            duration = int((service or {}).get("duration_min") or 60)
            window_label = f"{start.strftime('%-I:%M %p')}–{(start + timedelta(minutes=duration)).strftime('%-I:%M %p')}"
        else:
            warnings.append(reason)

    number = billing.next_job_number(db, business)
    job = models.Job(
        business_id=business.id,
        customer_id=customer.id if customer else None,
        number=number,
        service_key=(service or {}).get("key") or (service_key or "custom"),
        service_name=(service or {}).get("name") or (service_name or "Service request"),
        status=status,
        source=source,
        scheduled_start=start if status == "confirmed" else None,
        scheduled_end=(
            start + timedelta(minutes=int((service or {}).get("duration_min") or 60))
            if status == "confirmed" and start
            else None
        ),
        window_label=window_label,
        requested_for=requested_for or preferred_start,
        address=address or (customer.address_line1 if customer else None),
        price_estimate_low_cents=estimate_low_cents
        if estimate_low_cents is not None
        else (service or {}).get("price_min_cents"),
        price_estimate_high_cents=estimate_high_cents
        if estimate_high_cents is not None
        else (service or {}).get("price_max_cents"),
        notes=notes,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Tell the owner immediately; tell the customer what happens next.
    messaging.send_to_owner(
        db,
        business,
        messaging.tpl_job_booked_owner(business, job),
        template="job_booked_owner",
        job=job,
    )
    if customer:
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_customer_confirmation(business, job),
            template="job_confirmation",
            job=job,
        )
    return job, warnings


def confirm_job(
    db: Session, business: models.Business, job: models.Job, start: Optional[str] = None
) -> models.Job:
    if start:
        parsed = parse_datetime_loose(start, business)
        if parsed is None:
            raise BookingError("invalid_time")
        ok, reason = slot_is_available(
            business, parsed, job.service_key, active_jobs(db, business)
        )
        if not ok:
            raise BookingError(reason)
        duration = timedelta(
            minutes=int(
                (resolve_service(business, job.service_key, None) or {}).get("duration_min") or 60
            )
        )
        job.scheduled_start = parsed
        job.scheduled_end = parsed + duration
        job.window_label = (
            f"{parsed.strftime('%-I:%M %p')}–{(parsed + duration).strftime('%-I:%M %p')}"
        )

    if job.scheduled_start is None:
        raise BookingError("no_time_set")

    job.status = "confirmed"
    job.reminder_sent_at = None
    db.commit()
    db.refresh(job)

    messaging.send_to_owner(
        db,
        business,
        messaging.tpl_owner_job_confirmed(business, job),
        template="job_confirmed_owner",
        job=job,
    )
    if job.customer:
        messaging.send_to_customer(
            db,
            business,
            job.customer,
            messaging.tpl_customer_confirmation(business, job),
            template="job_confirmation",
            job=job,
        )
    return job


def cancel_job(db: Session, business: models.Business, job: models.Job, reason: str = "") -> models.Job:
    job.status = "cancelled"
    job.notes = f"{job.notes or ''}\nCancelled: {reason}".strip()
    db.commit()
    db.refresh(job)
    if job.customer:
        when = format_local(job.scheduled_start, business)
        messaging.send_to_customer(
            db,
            business,
            job.customer,
            f"{business.name}: your {job.service_name} on {when} has been cancelled. "
            f"Reply BOOK to find a new time.",
            template="job_cancelled",
            job=job,
        )
    return job


def complete_job(
    db: Session,
    business: models.Business,
    job: models.Job,
    *,
    amount_cents: Optional[int] = None,
    method: Optional[str] = None,
    already_paid: bool = False,
    via: str = "cash",
) -> models.Invoice:
    """Owner said "done": invoice the job and text the payment link."""
    if job.status not in ("paid", "invoiced", "done"):
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    existing = (
        db.query(models.Invoice)
        .filter(models.Invoice.business_id == business.id, models.Invoice.job_id == job.id)
        .order_by(models.Invoice.created_at.desc())
        .first()
    )
    if existing:
        return existing

    invoice = billing.build_invoice(
        db, business, job, amount_cents=amount_cents, method=method
    )
    if already_paid:
        return billing.mark_paid(db, business, invoice, via=via)
    return billing.issue_invoice(db, business, invoice)
