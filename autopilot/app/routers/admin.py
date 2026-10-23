"""Owner dashboard API. Everything here is tenant-scoped."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models
from ..availability import format_local, local_now, next_open_days, to_local
from ..config import settings
from ..db import get_db
from ..deps import current_business, owned_invoice, owned_job
from ..prompt import build_system_prompt, first_message_for
from ..tax import TAX_PROFILES, timezone_for_province
from ..services import billing, commands, jobs, voice_agent

router = APIRouter(prefix="/api", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class JobCreate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None
    service_key: Optional[str] = None
    service_name: Optional[str] = None
    preferred_start: Optional[str] = None
    requested_for: Optional[str] = None
    notes: Optional[str] = None
    source: str = "owner"


class JobPatch(BaseModel):
    price_final_cents: Optional[int] = None
    notes: Optional[str] = None
    requested_for: Optional[str] = None


class JobDone(BaseModel):
    amount_cents: Optional[int] = None
    method: Optional[str] = None
    already_paid: bool = False
    paid_via: str = "cash"


class JobConfirm(BaseModel):
    start: str


class InvoicePaid(BaseModel):
    via: str = "etransfer"


class BusinessPatch(BaseModel):
    name: Optional[str] = None
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    service_area: Optional[str] = None
    phone_number: Optional[str] = None
    greeting: Optional[str] = None
    tone: Optional[str] = None
    language: Optional[str] = None
    hours: Optional[dict] = None
    services: Optional[list] = None
    review_url: Optional[str] = None
    review_delay_days: Optional[int] = None
    rebook_enabled: Optional[bool] = None
    hst_enabled: Optional[bool] = None
    tax_profile: Optional[str] = None
    tax_number: Optional[str] = None
    etransfer_email: Optional[str] = None
    sms_footer: Optional[str] = None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def job_json(db: Session, business: models.Business, job: models.Job) -> dict:
    customer = job.customer
    invoice = (
        db.query(models.Invoice)
        .filter(models.Invoice.business_id == business.id, models.Invoice.job_id == job.id)
        .order_by(models.Invoice.created_at.desc())
        .first()
    )
    return {
        "id": job.id,
        "number": job.number,
        "status": job.status,
        "service": job.service_name,
        "service_key": job.service_key,
        "source": job.source,
        "scheduled_start": job.scheduled_start.isoformat() if job.scheduled_start else None,
        "scheduled_label": format_local(job.scheduled_start, business)
        if job.scheduled_start
        else None,
        "window_label": job.window_label,
        "requested_for": job.requested_for,
        "address": job.address or (customer.address_line1 if customer else None),
        "notes": job.notes,
        "estimate_low_cents": job.price_estimate_low_cents,
        "estimate_high_cents": job.price_estimate_high_cents,
        "price_final_cents": job.price_final_cents,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address_line1,
            "opted_out": customer.sms_opt_out_at is not None,
        }
        if customer
        else None,
        "invoice": invoice_json(invoice) if invoice else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


def invoice_json(invoice: models.Invoice) -> dict:
    return {
        "id": invoice.id,
        "number": invoice.number,
        "status": invoice.status,
        "method": invoice.method,
        "subtotal_cents": invoice.subtotal_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "tax_breakdown": invoice.tax_breakdown or [],
        "payment_url": invoice.payment_url,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "paid_via": invoice.paid_via,
        "reminders_sent": invoice.reminders_sent,
        "customer_name": invoice.customer.name if invoice.customer else None,
        "job_number": invoice.job.number if invoice.job else None,
        "service": invoice.job.service_name if invoice.job else None,
    }


# ---------------------------------------------------------------------------
# Business profile
# ---------------------------------------------------------------------------
@router.get("/me")
def me(business: models.Business = Depends(current_business)):
    return business_json(business)


def business_json(business: models.Business) -> dict:
    return {
        "id": business.id,
        "slug": business.slug,
        "name": business.name,
        "trade": business.trade,
        "owner_name": business.owner_name,
        "owner_phone": business.owner_phone,
        "owner_email": business.owner_email,
        "city": business.city,
        "province": business.province,
        "service_area": business.service_area,
        "phone_number": business.phone_number,
        "vapi_assistant_id": business.vapi_assistant_id,
        "greeting": business.greeting or first_message_for(business),
        "tone": business.tone,
        "language": business.language,
        "hours": business.hours or {},
        "services": business.services or [],
        "emergency_keywords": business.emergency_keywords or [],
        "review_url": business.review_url,
        "review_delay_days": business.review_delay_days,
        "rebook_enabled": business.rebook_enabled,
        "hst_enabled": business.hst_enabled,
        "tax_profile": business.tax_profile,
        "tax_rates": dict(TAX_PROFILES.get(business.tax_profile, [])),
        "tax_number": business.tax_number,
        "etransfer_email": business.etransfer_email,
        "sms_footer": business.sms_footer,
        "plan": business.plan,
        "plan_status": business.plan_status,
        "trial_ends_at": business.trial_ends_at.isoformat() if business.trial_ends_at else None,
        "minutes_included": business.minutes_included,
        "minutes_used": business.minutes_used,
        "timezone": timezone_for_province(business.province),
        "currency": business.currency,
        "demo_mode": settings.demo_mode,
        "integrations": {
            "sms": "dry_run" if settings.sms_dry_run else "twilio",
            "payments": "dry_run" if settings.payments_dry_run else "stripe",
            "voice": "configured" if settings.vapi_api_key else "dry_run",
        },
    }


@router.patch("/me")
def update_me(
    payload: BusinessPatch,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    data = payload.model_dump(exclude_unset=True)
    if "province" in data and data["province"]:
        data["province"] = data["province"].upper()[:2]
    for field, value in data.items():
        setattr(business, field, value)
    db.commit()
    db.refresh(business)
    return business_json(business)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    today = local_now(business).date()

    confirmed = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status.in_(("confirmed", "in_progress")),
        )
        .order_by(models.Job.scheduled_start.asc())
        .all()
    )
    today_jobs = [
        job
        for job in confirmed
        if job.scheduled_start and to_local(job.scheduled_start, business).date() == today
    ]
    upcoming = [
        job
        for job in confirmed
        if job.scheduled_start and job not in today_jobs
    ][:6]
    needs_action = (
        db.query(models.Job)
        .filter(
            models.Job.business_id == business.id,
            models.Job.status.in_(("requested", "needs_confirmation")),
        )
        .order_by(models.Job.created_at.desc())
        .limit(8)
        .all()
    )
    invoices = (
        db.query(models.Invoice)
        .filter(models.Invoice.business_id == business.id)
        .order_by(models.Invoice.created_at.desc())
        .all()
    )
    open_invoices = [i for i in invoices if i.status in ("sent", "overdue")]

    jobs_total = (
        db.query(func.count(models.Job.id))
        .filter(models.Job.business_id == business.id)
        .scalar()
        or 0
    )
    calls_recovered = (
        db.query(func.count(models.Call.id))
        .filter(
            models.Call.business_id == business.id,
            models.Call.job_id.isnot(None),
        )
        .scalar()
        or 0
    )
    calls_total = (
        db.query(func.count(models.Call.id))
        .filter(models.Call.business_id == business.id)
        .scalar()
        or 0
    )
    paid = [i for i in invoices if i.status == "paid" and i.paid_at]
    avg_days_to_pay = None
    if paid:
        spans = [
            max((i.paid_at - i.issued_at).total_seconds() / 86400, 0)
            if i.issued_at
            else 0
            for i in paid
        ]
        avg_days_to_pay = round(sum(spans) / len(spans), 1)

    summary = billing.tax_summary(business, invoices)
    recent_messages = (
        db.query(models.Message)
        .filter(models.Message.business_id == business.id)
        .order_by(models.Message.created_at.desc())
        .limit(12)
        .all()
    )

    return {
        "business": business_json(business),
        "today": [job_json(db, business, job) for job in today_jobs],
        "upcoming": [job_json(db, business, job) for job in upcoming],
        "needs_action": [job_json(db, business, job) for job in needs_action],
        "open_invoices": [invoice_json(i) for i in open_invoices],
        "stats": {
            "jobs_total": jobs_total,
            "calls_total": calls_total,
            "calls_recovered": calls_recovered,
            "recovered_rate": round(calls_recovered / calls_total, 2) if calls_total else 0,
            "revenue_cents": summary["revenue_cents"],
            "outstanding_cents": summary["outstanding_cents"],
            "avg_days_to_pay": avg_days_to_pay,
            "reviews_requested": (
                db.query(func.count(models.Job.id))
                .filter(
                    models.Job.business_id == business.id,
                    models.Job.review_requested_at.isnot(None),
                )
                .scalar()
                or 0
            ),
            "minutes_used": (
                db.query(func.coalesce(func.sum(models.Call.duration_seconds), 0))
                .filter(models.Call.business_id == business.id)
                .scalar()
                or 0
            )
            // 60,
        },
        "messages": [message_json(m) for m in recent_messages],
        "open_slots": next_open_days(
            business, jobs.active_jobs(db, business), days_ahead=5, per_day=2
        ),
        "demo_mode": settings.demo_mode,
    }


def message_json(message: models.Message) -> dict:
    return {
        "id": message.id,
        "direction": message.direction,
        "to": message.to_number,
        "from": message.from_number,
        "body": message.body,
        "template": message.template,
        "status": message.status,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@router.get("/jobs")
def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    query = db.query(models.Job).filter(models.Job.business_id == business.id)
    if status:
        query = query.filter(models.Job.status.in_(status.split(",")))
    rows = query.order_by(models.Job.created_at.desc()).limit(limit).all()
    return [job_json(db, business, job) for job in rows]


@router.post("/jobs", status_code=201)
def create_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    try:
        job, warnings = jobs.create_job(
            db,
            business,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            address=payload.address,
            service_key=payload.service_key,
            service_name=payload.service_name,
            preferred_start=payload.preferred_start,
            requested_for=payload.requested_for,
            notes=payload.notes,
            source=payload.source,
        )
    except jobs.BookingError as exc:
        raise HTTPException(400, exc.reason)
    return {**job_json(db, business, job), "warnings": warnings}


@router.get("/jobs/{job_ref}")
def get_job(
    job_ref: str,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    job = owned_job(db, business, job_ref)
    payload = job_json(db, business, job)
    calls = (
        db.query(models.Call)
        .filter(models.Call.business_id == business.id, models.Call.job_id == job.id)
        .all()
    )
    payload["calls"] = [
        {
            "id": call.id,
            "summary": call.summary,
            "transcript": call.transcript,
            "duration_seconds": call.duration_seconds,
        }
        for call in calls
    ]
    return payload


@router.patch("/jobs/{job_ref}")
def patch_job(
    job_ref: str,
    payload: JobPatch,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    job = owned_job(db, business, job_ref)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job_json(db, business, job)


@router.post("/jobs/{job_ref}/confirm")
def confirm_job(
    job_ref: str,
    payload: JobConfirm,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    job = owned_job(db, business, job_ref)
    try:
        jobs.confirm_job(db, business, job, payload.start)
    except jobs.BookingError as exc:
        raise HTTPException(409, exc.reason.replace("_", " "))
    db.refresh(job)
    return job_json(db, business, job)


@router.post("/jobs/{job_ref}/reschedule")
def reschedule_job(
    job_ref: str,
    payload: JobConfirm,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    return confirm_job(job_ref, payload, db, business)


@router.post("/jobs/{job_ref}/cancel")
def cancel_job(
    job_ref: str,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    job = owned_job(db, business, job_ref)
    jobs.cancel_job(db, business, job, reason="cancelled in dashboard")
    db.refresh(job)
    return job_json(db, business, job)


@router.post("/jobs/{job_ref}/done")
def done_job(
    job_ref: str,
    payload: JobDone,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    job = owned_job(db, business, job_ref)
    invoice = jobs.complete_job(
        db,
        business,
        job,
        amount_cents=payload.amount_cents,
        method=payload.method,
        already_paid=payload.already_paid,
        via=payload.paid_via,
    )
    db.refresh(job)
    db.refresh(invoice)
    return {"job": job_json(db, business, job), "invoice": invoice_json(invoice)}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
@router.get("/invoices")
def list_invoices(
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    query = db.query(models.Invoice).filter(models.Invoice.business_id == business.id)
    if status:
        query = query.filter(models.Invoice.status.in_(status.split(",")))
    rows = query.order_by(models.Invoice.created_at.desc()).limit(limit).all()
    return [invoice_json(invoice) for invoice in rows]


@router.post("/invoices/{invoice_ref}/send")
def send_invoice(
    invoice_ref: str,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    invoice = owned_invoice(db, business, invoice_ref)
    if invoice.status == "paid":
        raise HTTPException(409, "Invoice is already paid")
    billing.issue_invoice(db, business, invoice)
    db.refresh(invoice)
    return invoice_json(invoice)


@router.post("/invoices/{invoice_ref}/paid")
def mark_invoice_paid(
    invoice_ref: str,
    payload: InvoicePaid,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    invoice = owned_invoice(db, business, invoice_ref)
    billing.mark_paid(db, business, invoice, via=payload.via)
    db.refresh(invoice)
    return invoice_json(invoice)


@router.get("/invoices/{invoice_ref}")
def get_invoice(
    invoice_ref: str,
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    invoice = owned_invoice(db, business, invoice_ref)
    payload = invoice_json(invoice)
    payload["line_items"] = invoice.line_items or []
    payload["notes"] = invoice.notes
    payload["etransfer_email"] = invoice.etransfer_email
    payload["business_name"] = business.name
    payload["tax_number"] = business.tax_number
    return payload


# ---------------------------------------------------------------------------
# Customers, messages, availability
# ---------------------------------------------------------------------------
@router.get("/customers")
def list_customers(
    q: Optional[str] = None,
    limit: int = Query(100, le=300),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    query = db.query(models.Customer).filter(models.Customer.business_id == business.id)
    if q:
        needle = f"%{q}%"
        query = query.filter(
            or_(models.Customer.name.ilike(needle), models.Customer.phone.ilike(needle))
        )
    rows = query.order_by(models.Customer.created_at.desc()).limit(limit).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "address": c.address_line1,
            "consent": c.sms_consent and c.sms_opt_out_at is None,
            "opted_out": c.sms_opt_out_at is not None,
            "jobs": len(c.jobs),
        }
        for c in rows
    ]


@router.get("/messages")
def list_messages(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    rows = (
        db.query(models.Message)
        .filter(models.Message.business_id == business.id)
        .order_by(models.Message.created_at.desc())
        .limit(limit)
        .all()
    )
    return [message_json(m) for m in rows]


@router.get("/availability")
def availability(
    service_key: Optional[str] = None,
    days_ahead: int = Query(7, le=30),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    return {
        "timezone": timezone_for_province(business.province),
        "days": next_open_days(
            business,
            jobs.active_jobs(db, business),
            service_key=service_key,
            days_ahead=days_ahead,
            per_day=4,
        ),
    }


@router.get("/calls")
def list_calls(
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    rows = (
        db.query(models.Call)
        .filter(models.Call.business_id == business.id)
        .order_by(models.Call.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": call.id,
            "caller": call.caller_number,
            "direction": call.direction,
            "status": call.status,
            "duration_seconds": call.duration_seconds,
            "summary": call.summary,
            "job_id": call.job_id,
            "started_at": call.started_at.isoformat() if call.started_at else None,
        }
        for call in rows
    ]


@router.get("/commands")
def command_help(business: models.Business = Depends(current_business)):
    return {"help": commands.HELP_TEXT}


@router.get("/agent/prompt")
def agent_prompt(
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    return {
        "system_prompt": build_system_prompt(business),
        "first_message": business.greeting or first_message_for(business),
        "tools": voice_agent.TOOL_DEFINITIONS,
        "webhook_url": f"{settings.base_url}/webhooks/vapi",
        "assistant_payload": voice_agent.build_assistant_payload(business, settings.base_url),
    }


@router.post("/agent/provision")
def provision_agent(
    db: Session = Depends(get_db),
    business: models.Business = Depends(current_business),
):
    result = voice_agent.provision_assistant(business, settings.base_url)
    db.commit()
    return result
