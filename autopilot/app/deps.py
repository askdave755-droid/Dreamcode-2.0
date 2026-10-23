"""FastAPI dependencies. Every tenant-scoped route resolves the business here."""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db
from .phoneutil import normalize_phone
from .security import COOKIE_NAME, read_session_token


def current_business(
    request: Request, db: Session = Depends(get_db)
) -> models.Business:
    """Session cookie first, then the demo header (only when DEMO_MODE)."""
    token = request.cookies.get(COOKIE_NAME)
    business_id = read_session_token(token)

    if not business_id and settings.demo_mode:
        business_id = request.headers.get("X-Demo-Business")

    if not business_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    business = db.get(models.Business, business_id)
    if business is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown business")
    return business


def business_by_number(db: Session, number: Optional[str]) -> Optional[models.Business]:
    """Resolve an inbound/outbound phone number to its tenant."""
    normalized = normalize_phone(number)
    if not normalized:
        return None
    return (
        db.query(models.Business)
        .filter(models.Business.phone_number == normalized)
        .first()
    )


def business_or_404(db: Session, business_id: str) -> models.Business:
    business = db.get(models.Business, business_id)
    if business is None:
        raise HTTPException(404, "Business not found")
    return business


def owned_job(db: Session, business: models.Business, job_ref: str) -> models.Job:
    from .services.jobs import get_job

    job = get_job(db, business, job_ref)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def owned_invoice(db: Session, business: models.Business, invoice_ref: str) -> models.Invoice:
    from sqlalchemy import or_

    invoice = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.business_id == business.id,
            or_(models.Invoice.id == invoice_ref, models.Invoice.number == invoice_ref),
        )
        .first()
    )
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    return invoice
