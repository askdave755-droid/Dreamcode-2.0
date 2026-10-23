"""Time-based automation: reminders, chasers, reviews, rebooking.

Runs three ways, all through the same function:
  * in-process background loop (ENABLE_SCHEDULER=true)
  * Railway cron hitting POST /internal/run-scheduler
  * the test suite, directly

Every task is idempotent — it checks a timestamp before sending.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from . import messaging

log = logging.getLogger("autopilot.scheduler")

REMINDER_WINDOW_HOURS = 36
CHASE_INTERVAL_DAYS = 4
MAX_CHASES = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def send_job_reminders(db: Session, business: models.Business) -> int:
    now = _now()
    horizon = now + timedelta(hours=REMINDER_WINDOW_HOURS)
    jobs = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status == "confirmed",
            models.Job.scheduled_start.isnot(None),
            models.Job.reminder_sent_at.is_(None),
        )
        .all()
    )
    sent = 0
    for job in jobs:
        start = _aware(job.scheduled_start)
        if start is None or not (now <= start <= horizon):
            continue
        if job.customer is None:
            continue
        messaging.send_to_customer(
            db,
            business,
            job.customer,
            messaging.tpl_reminder(business, job),
            template="job_reminder",
            job=job,
        )
        job.reminder_sent_at = now
        db.commit()
        sent += 1
    return sent


def chase_unpaid_invoices(db: Session, business: models.Business) -> int:
    now = _now()
    invoices = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.business_id == business.id,
            models.Invoice.status.in_(("sent", "overdue")),
        )
        .all()
    )
    sent = 0
    for invoice in invoices:
        issued = _aware(invoice.issued_at)
        due = _aware(invoice.due_at)
        last = _aware(invoice.last_reminded_at)
        if issued is None or invoice.reminders_sent >= MAX_CHASES:
            continue
        if due and now > due and invoice.status == "sent":
            invoice.status = "overdue"
            db.commit()
        # First nudge waits until the due date; later nudges pace out.
        if due and now < due:
            continue
        if last and (now - last) < timedelta(days=CHASE_INTERVAL_DAYS):
            continue
        if issued and (now - issued) < timedelta(days=1):
            continue
        customer = db.get(models.Customer, invoice.customer_id) if invoice.customer_id else None
        job = db.get(models.Job, invoice.job_id) if invoice.job_id else None
        if customer is None:
            continue
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_payment_reminder(business, invoice, job),
            template="payment_reminder",
            job=job,
            invoice=invoice,
        )
        invoice.reminders_sent += 1
        invoice.last_reminded_at = now
        db.commit()
        sent += 1
    return sent


def send_review_requests(db: Session, business: models.Business) -> int:
    if not business.review_url:
        return 0
    now = _now()
    delay = timedelta(days=int(business.review_delay_days or 2))
    paid = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.business_id == business.id,
            models.Invoice.status == "paid",
        )
        .all()
    )
    sent = 0
    for invoice in paid:
        paid_at = _aware(invoice.paid_at)
        if paid_at is None or now < paid_at + delay:
            continue
        job = db.get(models.Job, invoice.job_id) if invoice.job_id else None
        if job is None or job.review_requested_at is not None:
            continue
        customer = db.get(models.Customer, invoice.customer_id) if invoice.customer_id else None
        if customer is None:
            continue
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_review(business, customer),
            template="review_request",
            job=job,
            invoice=invoice,
        )
        job.review_requested_at = now
        db.commit()
        sent += 1
    return sent


def send_rebook_texts(db: Session, business: models.Business) -> int:
    if not business.rebook_enabled:
        return 0
    now = _now()
    jobs = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.rebook_due_at.isnot(None),
            models.Job.rebook_due_at <= now,
            models.Job.rebook_sent_at.is_(None),
        )
        .all()
    )
    sent = 0
    for job in jobs:
        customer = db.get(models.Customer, job.customer_id) if job.customer_id else None
        if customer is None or customer.sms_opt_out_at is not None:
            job.rebook_sent_at = now
            db.commit()
            continue
        messaging.send_to_customer(
            db,
            business,
            customer,
            messaging.tpl_rebook(business, job, customer),
            template="rebook",
            job=job,
        )
        job.rebook_sent_at = now
        db.commit()
        sent += 1
    return sent


def notify_trial_ending(db: Session, business: models.Business) -> int:
    if business.plan != "trial" or not business.trial_ends_at:
        return 0
    now = _now()
    ends = _aware(business.trial_ends_at)
    already = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == business.id,
            models.Message.template == "trial_ending",
        )
        .count()
    )
    if already or ends is None or ends > now + timedelta(days=3):
        return 0
    days = max(int((ends - now).total_seconds() // 86400), 0)
    messaging.send_to_owner(
        db,
        business,
        f"Your free trial ends in {days} day(s). Reply PLAN to see options and keep "
        f"your line live.",
        template="trial_ending",
    )
    return 1


def run_due_tasks(db: Session, business_id: Optional[str] = None) -> dict:
    """Run every due task. Safe to call repeatedly."""
    query = db.query(models.Business).filter(models.Business.paused.is_(False))
    if business_id:
        query = query.filter(models.Business.id == business_id)
    totals = {"reminders": 0, "chases": 0, "reviews": 0, "rebook": 0, "trial": 0}
    for business in query.all():
        try:
            totals["reminders"] += send_job_reminders(db, business)
            totals["chases"] += chase_unpaid_invoices(db, business)
            totals["reviews"] += send_review_requests(db, business)
            totals["rebook"] += send_rebook_texts(db, business)
            totals["trial"] += notify_trial_ending(db, business)
        except Exception as exc:  # one bad tenant must not stop the others
            db.rollback()
            log.exception("Scheduler failed for business %s: %s", business.id, exc)
    return totals


def start_background_loop(interval_seconds: int = 300) -> threading.Thread:
    from ..db import SessionLocal

    def loop():
        while True:
            time.sleep(interval_seconds)
            session = SessionLocal()
            try:
                result = run_due_tasks(session)
                if any(result.values()):
                    log.info("Scheduler run: %s", result)
            except Exception as exc:
                log.warning("Scheduler loop error: %s", exc)
            finally:
                session.close()

    thread = threading.Thread(target=loop, name="autopilot-scheduler", daemon=True)
    thread.start()
    log.info("Scheduler loop started (every %ss)", interval_seconds)
    return thread
