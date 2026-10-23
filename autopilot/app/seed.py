"""Demo tenant so the product can be clicked through on a fresh clone.

Idempotent: re-running only fills in what is missing.
"""
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import models
from .config import settings
from .db import SessionLocal
from .services import billing, onboarding

log = logging.getLogger("autopilot.seed")

DEMO_SLUG = "levesque-deneigement"
TZ = ZoneInfo("America/Toronto")


def _local(year, month, day, hour, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


def seed_demo() -> models.Business:
    db = SessionLocal()
    try:
        existing = (
            db.query(models.Business).filter(models.Business.slug == DEMO_SLUG).first()
        )
        if existing:
            return existing

        today = datetime.now(TZ).date()
        business = onboarding.create_business(
            db,
            name="Lévesque Déneigement",
            owner_name="Marc Lévesque",
            owner_phone="+14185550199",
            trade="snow_removal",
            city="Saint-Georges",
            province="QC",
            service_area="Saint-Georges, Beauceville, and Sainte-Marie",
            phone_number="+14185550123",
            owner_email="marc@example.com",
            review_url="https://g.page/r/example-review-link",
            etransfer_email="marc@example.com",
            tax_number="1234567890 TQ0001",
            greeting=(
                "Lévesque Déneigement, bonjour! This is Marc's AI assistant. "
                "Are you calling about a driveway, or something urgent?"
            ),
            plan="starter",
        )
        business.plan_status = "active"
        business.minutes_included = 200
        business.trial_ends_at = None
        business.sms_footer = "Reply STOP to opt out."
        business.language = "bilingual"
        db.commit()

        customers = []
        for name, phone, address in [
            ("Chantal Gagnon", "+14185550111", "1240 3e Avenue, Saint-Georges"),
            ("Patrick Roy", "+14185550122", "88 Rue Lamartine, Beauceville"),
            ("Sylvie Fortin", "+14185550133", "455 Route Kennedy, Sainte-Marie"),
            ("Jean-Marc Boucher", "+14185550144", "12 Rue des Érables, Saint-Georges"),
        ]:
            customers.append(
                models.Customer(
                    business_id=business.id,
                    name=name,
                    phone=phone,
                    address_line1=address,
                    city="Saint-Georges",
                    sms_consent=True,
                    sms_consent_source="voice_call",
                    sms_consent_at=datetime.now(timezone.utc) - timedelta(days=30),
                )
            )
        db.add_all(customers)
        db.commit()
        for customer in customers:
            db.refresh(customer)

        def add_job(number, customer, service_key, start, status, source="voice", notes=None):
            service = onboarding.services_for_trade("snow_removal")
            match = next(s for s in service if s["key"] == service_key)
            job = models.Job(
                business_id=business.id,
                customer_id=customer.id,
                number=number,
                service_key=service_key,
                service_name=match["name"],
                status=status,
                source=source,
                scheduled_start=start,
                scheduled_end=start + timedelta(minutes=match["duration_min"]),
                window_label=start.strftime("%-I:%M %p"),
                address=customer.address_line1,
                price_estimate_low_cents=match["price_min_cents"],
                price_estimate_high_cents=match["price_max_cents"],
                price_final_cents=match["price_min_cents"]
                if status in ("done", "paid")
                else None,
                notes=notes,
                completed_at=start + timedelta(hours=1) if status in ("done", "paid") else None,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job

        # Today: two confirmed jobs, one already finished this morning.
        job1 = add_job(1, customers[0], "driveway", _local(today.year, today.month, today.day, 8), "paid")
        job2 = add_job(2, customers[1], "walkway", _local(today.year, today.month, today.day, 11), "confirmed")
        add_job(3, customers[2], "driveway", _local(today.year, today.month, today.day, 14), "confirmed")
        # Tomorrow and the day after.
        tomorrow = today + timedelta(days=1)
        add_job(4, customers[3], "salting", _local(tomorrow.year, tomorrow.month, tomorrow.day, 9), "confirmed")
        later = today + timedelta(days=3)
        add_job(5, customers[0], "driveway", _local(later.year, later.month, later.day, 10), "confirmed")
        # Waiting on the owner.
        add_job(
            6,
            customers[1],
            "seasonal",
            _local(today.year, today.month, today.day, 16),
            "needs_confirmation",
            notes="Caller wants a seasonal contract for a long double driveway. Call back with a firm price.",
        )

        # One invoice already paid (drives the review + rebook flow), one open.
        invoice = billing.build_invoice(
            db, business, job1, amount_cents=7500, method="stripe"
        )
        invoice.status = "sent"
        invoice.issued_at = datetime.now(timezone.utc) - timedelta(days=3)
        invoice.payment_url = f"{settings.base_url}/pay/{invoice.id}"
        invoice.stripe_session_id = f"demo_{invoice.id}"
        db.commit()
        billing.mark_paid(db, business, invoice, via="stripe")
        job1.paid_at = invoice.paid_at
        job1.review_requested_at = datetime.now(timezone.utc) - timedelta(days=1)
        job1.rebook_due_at = datetime.now(timezone.utc) + timedelta(days=4)
        db.commit()

        open_invoice = billing.build_invoice(
            db, business, job2, amount_cents=4500, method="stripe"
        )
        open_invoice.status = "sent"
        open_invoice.issued_at = datetime.now(timezone.utc) - timedelta(days=4)
        open_invoice.due_at = datetime.now(timezone.utc) - timedelta(days=1)
        open_invoice.payment_url = f"{settings.base_url}/pay/{open_invoice.id}"
        open_invoice.stripe_session_id = f"demo_{open_invoice.id}"
        db.commit()

        # A call that turned into a job — the headline metric.
        call = models.Call(
            business_id=business.id,
            customer_id=customers[3].id,
            job_id=job1.id,
            provider="vapi",
            provider_call_id="demo-call-1",
            caller_number=customers[3].phone,
            called_number=business.phone_number,
            direction="in",
            status="completed",
            duration_seconds=182,
            summary=(
                "Caller booked a driveway clearing for Monday 8am at 12 Rue des Érables. "
                "Quoted the usual $45–$95 range; owner confirms final price."
            ),
            transcript=(
                "AI: Lévesque Déneigement, this is Marc's AI assistant. How can I help?\n"
                "Caller: I need my driveway done Monday morning.\n"
                "AI: Happy to book that. What's the address?\n"
                "Caller: 12 Rue des Érables in Saint-Georges.\n"
                "AI: A single driveway usually runs $45 to $95 and Marc confirms the exact price. "
                "I have Monday at 8am open — does that work?\n"
                "Caller: Perfect.\n"
                "AI: You're booked. I'll text you a confirmation now."
            ),
            tool_calls=[
                {"name": "check_availability", "arguments": {"service_key": "driveway"}},
                {"name": "book_job", "arguments": {"service_key": "driveway"}},
            ],
            started_at=datetime.now(timezone.utc) - timedelta(days=2, hours=3),
            ended_at=datetime.now(timezone.utc) - timedelta(days=2, hours=3) + timedelta(seconds=182),
        )
        db.add(call)
        db.commit()

        log.info("Seeded demo business %s", business.name)
        return business
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
    print("Demo business ready. Sign in with owner phone +14185550199.")
