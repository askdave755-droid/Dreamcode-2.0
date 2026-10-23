"""Owner signup, onboarding, and passwordless login."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..phoneutil import normalize_phone
from ..security import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    hash_code,
    make_session_token,
    new_code,
    verify_code,
)
from ..services import messaging, onboarding
from ..tax import PROVINCE_PROFILES, TAX_PROFILES, timezone_for_province

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupPayload(BaseModel):
    business_name: str = Field(min_length=2, max_length=160)
    owner_name: str = Field(min_length=1, max_length=120)
    owner_phone: str
    trade: str = "snow_removal"
    city: Optional[str] = None
    province: str = "QC"
    service_area: Optional[str] = None
    phone_number: Optional[str] = None
    owner_email: Optional[str] = None
    review_url: Optional[str] = None
    etransfer_email: Optional[str] = None
    greeting: Optional[str] = None
    hst_enabled: bool = True


class CodeRequest(BaseModel):
    phone: str


class CodeVerify(BaseModel):
    phone: str
    code: str


def _set_session(response: Response, business: models.Business) -> str:
    token = make_session_token(business.id)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
    )
    return token


@router.get("/options")
def onboarding_options():
    return {
        "trades": [
            {
                "key": key,
                "label": preset["label"],
                "tagline": preset["tagline"],
                "services": preset["services"],
                "example_greeting": None,
            }
            for key, preset in onboarding.TRADE_PRESETS.items()
        ],
        "provinces": [
            {"code": code, "tax_profile": profile, "rates": TAX_PROFILES.get(profile, [])}
            for code, profile in sorted(PROVINCE_PROFILES.items())
        ],
        "default_hours": onboarding.DEFAULT_HOURS,
    }


@router.post("/signup")
def signup(payload: SignupPayload, response: Response, db: Session = Depends(get_db)):
    """Create a business from the onboarding form and sign the owner in."""
    if not normalize_phone(payload.owner_phone):
        raise HTTPException(400, "Enter a valid 10-digit Canadian mobile number")
    if payload.trade not in onboarding.TRADE_PRESETS:
        raise HTTPException(400, "Unknown trade")

    business = onboarding.create_business(
        db,
        name=payload.business_name,
        owner_name=payload.owner_name,
        owner_phone=payload.owner_phone,
        trade=payload.trade,
        city=payload.city,
        province=payload.province,
        service_area=payload.service_area,
        phone_number=payload.phone_number,
        owner_email=payload.owner_email,
        review_url=payload.review_url,
        etransfer_email=payload.etransfer_email,
        greeting=payload.greeting,
        hst_enabled=payload.hst_enabled,
    )
    token = _set_session(response, business)

    messaging.send_to_owner(
        db,
        business,
        f"Welcome to Autopilot, {business.owner_name}! Your AI receptionist is ready. "
        f"Text HELP for commands, TODAY for your schedule.",
        template="welcome",
    )

    return {
        "business": _public_business(business),
        "token": token if settings.demo_mode else None,
    }


@router.post("/request-code")
def request_code(payload: CodeRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(400, "Enter a valid Canadian mobile number")

    business = (
        db.query(models.Business).filter(models.Business.owner_phone == phone).first()
    )
    # Always answer the same way so this endpoint cannot enumerate customers.
    generic = {"sent": True, "message": "If that number has an account, a code is on its way."}
    if business is None:
        return generic

    code = new_code()
    db.add(
        models.LoginCode(
            business_id=business.id,
            phone=phone,
            code_hash=hash_code(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    )
    db.commit()
    messaging.send_to_owner(
        db,
        business,
        f"{code} is your Autopilot login code. It expires in 10 minutes. "
        f"If you didn't ask for this, ignore it.",
        template="login_code",
    )
    if settings.demo_mode:
        generic["demo_code"] = code
    return generic


@router.post("/verify")
def verify(payload: CodeVerify, response: Response, db: Session = Depends(get_db)):
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(400, "Invalid number")
    business = (
        db.query(models.Business).filter(models.Business.owner_phone == phone).first()
    )
    if business is None:
        raise HTTPException(400, "Code is invalid or expired")

    now = datetime.now(timezone.utc)
    codes = (
        db.query(models.LoginCode)
        .filter(
            models.LoginCode.business_id == business.id,
            models.LoginCode.used_at.is_(None),
        )
        .order_by(models.LoginCode.created_at.desc())
        .limit(5)
        .all()
    )
    match = next(
        (
            record
            for record in codes
            if verify_code(payload.code.strip(), record.code_hash)
            and _aware(record.expires_at) > now
        ),
        None,
    )
    if match is None:
        raise HTTPException(400, "Code is invalid or expired")
    match.used_at = now
    db.commit()

    token = _set_session(response, business)
    return {"business": _public_business(business), "token": token if settings.demo_mode else None}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.api_route("/demo", methods=["GET", "POST"])
def demo_login(response: Response, db: Session = Depends(get_db)):
    """One-click demo tenancy. Disabled outside DEMO_MODE."""
    if not settings.demo_mode:
        raise HTTPException(404, "Not found")
    business = db.query(models.Business).order_by(models.Business.created_at.asc()).first()
    if business is None:
        raise HTTPException(404, "No demo business seeded")
    token = _set_session(response, business)
    return {"business": _public_business(business), "token": token}


def _aware(value):
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _public_business(business: models.Business) -> dict:
    return {
        "id": business.id,
        "slug": business.slug,
        "name": business.name,
        "trade": business.trade,
        "owner_name": business.owner_name,
        "owner_phone": business.owner_phone,
        "phone_number": business.phone_number,
        "city": business.city,
        "province": business.province,
        "timezone": timezone_for_province(business.province),
        "plan": business.plan,
        "plan_status": business.plan_status,
        "trial_ends_at": business.trial_ends_at,
        "greeting": business.greeting,
        "review_url": business.review_url,
    }
