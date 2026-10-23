"""End-to-end workflow tests: book → invoice → pay → review → rebook."""
from datetime import date, datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from app import models
from app.phoneutil import normalize_phone
from app.services import billing, commands, jobs, scheduler
from app.services import onboarding

TZ = ZoneInfo("America/Toronto")


def _next_workday(hour=10, days=2):
    day = date.today() + timedelta(days=days)
    while day.weekday() == 6:  # Sunday is closed by default
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, tzinfo=TZ)


def _customer(db, business, phone="+14185550222", name="Test Customer"):
    return jobs.get_or_create_customer(
        db, business, phone, name=name, address="12 Rue Test, Saint-Georges"
    )


def test_phone_normalization():
    assert normalize_phone("(418) 555-0123") == "+14185550123"
    assert normalize_phone("1 418 555 0123") == "+14185550123"
    assert normalize_phone("+1 418-555-0123") == "+14185550123"
    assert normalize_phone("") is None


def test_booking_confirms_when_slot_is_free(db, business):
    start = _next_workday()
    job, warnings = jobs.create_job(
        db,
        business,
        customer_name="Marie Côté",
        customer_phone="(418) 555-0222",
        address="9 Rue des Tests",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    assert job.status == "confirmed"
    assert warnings == []
    assert job.number == 1
    assert job.customer.phone == "+14185550222"

    # Owner and customer both get a text.
    templates = [
        message.template
        for message in db.query(models.Message)
        .filter(models.Message.business_id == business.id)
        .all()
    ]
    assert "job_booked_owner" in templates
    assert "job_confirmation" in templates


def test_double_booking_falls_back_to_callback(db, business):
    start = _next_workday()
    jobs.create_job(
        db,
        business,
        customer_name="First",
        customer_phone="+14185550301",
        address="1 A Street",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    second, warnings = jobs.create_job(
        db,
        business,
        customer_name="Second",
        customer_phone="+14185550302",
        address="2 B Street",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    assert second.status == "needs_confirmation"
    assert "slot_taken" in warnings
    assert second.scheduled_start is None


def test_unknown_service_without_name_is_rejected(db, business):
    try:
        jobs.create_job(db, business, customer_phone="+14185550303", service_key="nope")
    except jobs.BookingError as exc:
        assert exc.reason == "unknown_service"
    else:
        raise AssertionError("expected BookingError")


def test_complete_job_creates_invoice_with_tax_and_link(db, business):
    start = _next_workday()
    job, _ = jobs.create_job(
        db,
        business,
        customer_name="Luc Bergeron",
        customer_phone="+14185550304",
        address="77 Rue Principale",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    invoice = jobs.complete_job(db, business, job, amount_cents=8000, method="stripe")
    assert invoice.subtotal_cents == 8000
    assert invoice.tax_cents == 400 + 798
    assert invoice.total_cents == 9198
    assert invoice.status == "sent"
    assert invoice.payment_url and invoice.stripe_session_id
    assert invoice.number.startswith("INV-")

    db.refresh(job)
    assert job.status == "done"

    # Idempotent: texting DONE twice does not duplicate.
    again = jobs.complete_job(db, business, job, amount_cents=8000)
    assert again.id == invoice.id


def test_mark_paid_is_idempotent_and_schedules_followups(db, business):
    start = _next_workday()
    job, _ = jobs.create_job(
        db,
        business,
        customer_name="Sophie Lavoie",
        customer_phone="+14185550305",
        address="5 Avenue",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    invoice = jobs.complete_job(db, business, job, amount_cents=7000)

    billing.mark_paid(db, business, invoice, via="etransfer")
    billing.mark_paid(db, business, invoice, via="etransfer")  # second time is a no-op

    db.refresh(invoice)
    db.refresh(job)
    assert invoice.status == "paid"
    assert job.status == "paid"
    # Driveway clearing has rebook_after_days=0 (it is storm-driven, not seasonal).
    assert job.rebook_due_at is None
    receipts = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == business.id,
            models.Message.template == "paid_receipt",
        )
        .count()
    )
    assert receipts == 1


def test_owner_done_command_with_amount(db, business):
    start = _next_workday()
    job, _ = jobs.create_job(
        db,
        business,
        customer_name="Owner Command",
        customer_phone="+14185550306",
        address="8 Rue",
        service_key="walkway",
        preferred_start=start.isoformat(),
    )
    reply = commands.handle_inbound(
        db,
        business,
        business.owner_phone,
        business.phone_number,
        f"DONE {job.number} 145",
    )
    assert "INV-" in reply
    db.refresh(job)
    invoice = (
        db.query(models.Invoice)
        .filter(models.Invoice.business_id == business.id, models.Invoice.job_id == job.id)
        .first()
    )
    assert invoice.subtotal_cents == 14500


def test_owner_paid_command_and_agenda(db, business):
    start = _next_workday()
    job, _ = jobs.create_job(
        db,
        business,
        customer_name="Paid By Owner",
        customer_phone="+14185550307",
        address="9 Rue",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    invoice = jobs.complete_job(db, business, job, amount_cents=6000)
    reply = commands.handle_owner_message(db, business, f"PAID {invoice.number}")
    assert "Marked" in reply
    db.refresh(invoice)
    assert invoice.status == "paid"

    agenda = commands.handle_owner_message(db, business, "TODAY")
    assert isinstance(agenda, str) and agenda


def test_customer_stop_opts_out_and_blocks_messages(db, business):
    customer = _customer(db, business, "+14185550308", "Opt Out")
    reply = commands.handle_customer_message(db, business, customer, "STOP")
    assert "unsubscribed" in reply.lower()
    db.refresh(customer)
    assert customer.sms_opt_out_at is not None

    from app.services import messaging

    result = messaging.send_to_customer(db, business, customer, "hello")
    assert result is None  # skipped, not sent
    skipped = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == business.id,
            models.Message.customer_id == customer.id,
            models.Message.status == "skipped_opt_out",
        )
        .count()
    )
    assert skipped == 1


def test_scheduler_sends_reminder_review_and_rebook(db, business):
    now = datetime.now(timezone.utc)
    customer = _customer(db, business, "+14185550309", "Scheduler Test")
    start = now + timedelta(hours=20)
    job = models.Job(
        business_id=business.id,
        customer_id=customer.id,
        number=77,
        service_key="driveway",
        service_name="Driveway clearing",
        status="confirmed",
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=45),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    assert scheduler.send_job_reminders(db, business) == 1
    db.refresh(job)
    assert job.reminder_sent_at is not None

    invoice = models.Invoice(
        business_id=business.id,
        job_id=job.id,
        customer_id=customer.id,
        number="INV-9001",
        status="paid",
        subtotal_cents=5000,
        tax_cents=749,
        total_cents=5749,
        issued_at=now - timedelta(days=5),
        paid_at=now - timedelta(days=4),
    )
    db.add(invoice)
    job.status = "paid"
    job.rebook_due_at = now - timedelta(days=1)
    db.commit()

    assert scheduler.send_review_requests(db, business) == 1
    assert scheduler.send_rebook_texts(db, business) == 1
    db.refresh(job)
    assert job.review_requested_at is not None
    assert job.rebook_sent_at is not None


def test_scheduler_chases_unpaid_invoice_once_per_interval(db, business):
    now = datetime.now(timezone.utc)
    customer = _customer(db, business, "+14185550310", "Chaser Test")
    invoice = models.Invoice(
        business_id=business.id,
        customer_id=customer.id,
        number="INV-9002",
        status="sent",
        subtotal_cents=5000,
        tax_cents=749,
        total_cents=5749,
        issued_at=now - timedelta(days=10),
        due_at=now - timedelta(days=3),
    )
    db.add(invoice)
    db.commit()

    assert scheduler.chase_unpaid_invoices(db, business) == 1
    assert scheduler.chase_unpaid_invoices(db, business) == 0  # paced
    db.refresh(invoice)
    assert invoice.status == "overdue"
    assert invoice.reminders_sent == 1


def test_tax_summary_separates_components(db, business):
    now = datetime.now(timezone.utc)
    db.add(
        models.Invoice(
            business_id=business.id,
            number="INV-9100",
            status="paid",
            subtotal_cents=10000,
            tax_cents=1498,
            total_cents=11498,
            tax_breakdown=[
                {"label": "GST", "rate": 0.05, "amount_cents": 500},
                {"label": "QST", "rate": 0.09975, "amount_cents": 998},
            ],
            paid_at=now,
        )
    )
    db.commit()
    invoices = (
        db.query(models.Invoice).filter(models.Invoice.business_id == business.id).all()
    )
    summary = billing.tax_summary(business, invoices)
    assert summary["gst_cents"] == 500
    assert summary["qst_cents"] == 998
    assert summary["revenue_cents"] == 11498


def test_text_onboarding_creates_business(db):
    draft, question = onboarding.start_text_onboarding(db, "(418) 555-0777")
    assert "trade" in question.lower()

    answers = ["1", "Onboarding Snow", "Test Owner", "Beauceville", "Beauce", "ALL", "SKIP"]
    result = None
    for answer in answers:
        result = onboarding.advance_text_onboarding(db, draft, answer)
    assert result["business_created"] is True
    created = result["business"]
    assert created.name == "Onboarding Snow"
    assert created.owner_phone == "+14185550777"
    assert created.province == "QC"
    assert created.services


def test_etransfer_without_address_falls_back_to_card_link(db, business):
    business.etransfer_email = None
    db.commit()
    start = _next_workday()
    job, _ = jobs.create_job(
        db,
        business,
        customer_name="No Etransfer",
        customer_phone="+14185550311",
        address="3 Rue",
        service_key="driveway",
        preferred_start=start.isoformat(),
    )
    invoice = jobs.complete_job(db, business, job, amount_cents=5000, method="etransfer")
    assert invoice.method == "stripe"
    assert invoice.payment_url


def test_prompt_carries_disclosure_and_range_guardrails(business):
    from app.prompt import build_system_prompt

    prompt = build_system_prompt(business)
    assert "AI assistant" in prompt
    assert "Never quote a firm price" in prompt
    assert business.name in prompt
    assert "$45" in prompt and "$95" in prompt  # driveway range rendered
    assert "escalate_to_owner" in prompt
