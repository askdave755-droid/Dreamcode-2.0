"""Twilio SMS webhooks: inbound commands and delivery receipts."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_db
from ..deps import business_by_number
from ..phoneutil import normalize_phone
from ..security import verify_twilio_signature
from ..services import commands, messaging, onboarding

log = logging.getLogger("autopilot.sms")
router = APIRouter(tags=["sms"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def twiml(message: Optional[str]) -> Response:
    if not message:
        return Response(content=EMPTY_TWIML, media_type="application/xml")
    escaped = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{escaped}</Message></Response>"
    )
    return Response(content=body, media_type="application/xml")


@router.post("/webhooks/twilio/sms")
async def twilio_inbound(
    request: Request,
    db: Session = Depends(get_db),
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(""),
    MessageSid: str = Form(""),
):
    form = {"From": From, "To": To, "Body": Body, "MessageSid": MessageSid, "NumMedia": "0"}
    form.update({key: value for key, value in (await request.form()).items() if isinstance(value, str)})

    signature = request.headers.get("X-Twilio-Signature")
    candidates = [str(request.url)]
    if settings.public_base_url:
        candidates.append(f"{settings.public_base_url.rstrip('/')}/webhooks/twilio/sms")
    if not any(verify_twilio_signature(url, form, signature) for url in candidates):
        log.warning("Rejected Twilio webhook with bad signature")
        return Response(status_code=403)

    body = (Body or "").strip()
    business = business_by_number(db, To)

    if business is None:
        # Is this someone halfway through text onboarding?
        draft = (
            db.query(models.OnboardingDraft)
            .filter(models.OnboardingDraft.phone == (normalize_phone(From) or From))
            .order_by(models.OnboardingDraft.created_at.desc())
            .first()
        )
        if draft and draft.step != "done":
            result = onboarding.advance_text_onboarding(db, draft, body)
            return twiml(result["reply"])
        return twiml(
            "This number belongs to an Autopilot business line that isn't connected yet. "
            "Reply HELP for setup help."
        )

    messaging.record(
        db,
        business,
        direction="in",
        to_number=business.phone_number or To,
        from_number=normalize_phone(From) or From,
        body=body,
        template="inbound",
        status="received",
        provider_sid=MessageSid or None,
    )

    try:
        reply = commands.handle_inbound(db, business, From, To, body)
    except Exception as exc:  # never let a command error look like silence
        db.rollback()
        log.exception("Inbound SMS handling failed: %s", exc)
        reply = f"Sorry — something went wrong on our end. {business.owner_name} has been notified."

    return twiml(reply)


@router.post("/webhooks/twilio/status")
async def twilio_status(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    sid = form.get("MessageSid") or form.get("SmsSid")
    status = form.get("MessageStatus") or form.get("SmsStatus") or "unknown"
    if sid:
        message = (
            db.query(models.Message)
            .filter(models.Message.provider_sid == sid)
            .first()
        )
        if message:
            message.status = status
            db.commit()
    return Response(content=EMPTY_TWIML, media_type="application/xml")


@router.post("/webhooks/twilio/voice")
async def twilio_voice_fallback(To: str = Form(""), From: str = Form("")):
    """Fallback for a line whose voice provider is not wired yet.

    Keeps the missed call from disappearing: the caller hears a promise, and the
    owner gets the number in the call log.
    """
    return Response(
        content=(
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say voice=\"Polly.Joanna\">"
            "You've reached a business line. Please send a text message to this number "
            "and the owner will get back to you shortly."
            "</Say></Response>"
        ),
        media_type="application/xml",
    )
