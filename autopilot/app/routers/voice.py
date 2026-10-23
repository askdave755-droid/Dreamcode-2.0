"""Voice-agent webhooks (Vapi primary, Bland adapter).

Vapi calls one URL for everything and puts the event type in `message.type`.
Tool invocations must be answered synchronously with a JSON body, which is why
the handlers here do their work inline rather than in a background task.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..availability import format_local, next_open_days
from ..config import settings
from ..db import get_db
from ..deps import business_by_number
from ..phoneutil import format_phone, normalize_phone
from ..tax import timezone_for_province
from ..security import verify_vapi_secret
from ..services import jobs, messaging
from ..services.voice_agent import build_assistant_payload

log = logging.getLogger("autopilot.voice")
router = APIRouter(tags=["voice"])


def _text(value: Any) -> str:
    return json.dumps(value, default=str)


def resolve_business_for_call(db: Session, payload: dict) -> Optional[models.Business]:
    message = payload.get("message", payload)
    call = message.get("call") or {}
    metadata = (call.get("metadata") or message.get("metadata") or {})

    business_id = metadata.get("business_id")
    if business_id:
        business = db.get(models.Business, business_id)
        if business:
            return business

    for candidate in (
        (call.get("phoneNumber") or {}).get("number"),
        message.get("phoneNumber"),
        (message.get("customer") or {}).get("number"),
        payload.get("to"),
        payload.get("phone_number"),
    ):
        business = business_by_number(db, candidate)
        if business:
            return business

    assistant_id = call.get("assistantId") or message.get("assistantId") or payload.get("assistant_id")
    if assistant_id:
        business = (
            db.query(models.Business)
            .filter(models.Business.vapi_assistant_id == assistant_id)
            .first()
        )
        if business:
            return business
    return None


def upsert_call(db: Session, business: models.Business, payload: dict) -> models.Call:
    message = payload.get("message", payload)
    call_data = message.get("call") or {}
    provider_call_id = (
        call_data.get("id")
        or message.get("call_id")
        or message.get("callId")
        or payload.get("call_id")
    )
    customer_number = normalize_phone(
        (call_data.get("customer") or {}).get("number")
        or message.get("customer_number")
        or payload.get("from")
    )

    call = None
    if provider_call_id:
        call = (
            db.query(models.Call)
            .filter(
                models.Call.business_id == business.id,
                models.Call.provider_call_id == provider_call_id,
            )
            .first()
        )
    if call is None:
        call = models.Call(
            business_id=business.id,
            provider_call_id=provider_call_id,
            provider="bland" if "bland" in str(payload.get("provider", "vapi")).lower() else "vapi",
            caller_number=customer_number,
            direction="in",
            status="in_progress",
            started_at=datetime.now(timezone.utc),
        )
        db.add(call)

    if customer_number:
        customer = (
            db.query(models.Customer)
            .filter(
                models.Customer.business_id == business.id,
                models.Customer.phone == customer_number,
            )
            .first()
        )
        if customer:
            call.customer_id = customer.id

    artifact = message.get("artifact") or {}
    analysis = message.get("analysis") or {}
    if artifact.get("transcript") or message.get("transcript"):
        call.transcript = artifact.get("transcript") or message.get("transcript")
    if artifact.get("recordingUrl") or message.get("recording_url"):
        call.recording_url = artifact.get("recordingUrl") or message.get("recording_url")
    summary = (
        analysis.get("summary")
        or message.get("summary")
        or payload.get("summary")
    )
    if summary:
        call.summary = summary

    duration = call_data.get("durationSeconds") or message.get("duration_seconds") or 0
    if duration:
        call.duration_seconds = int(duration)
    db.commit()
    db.refresh(call)
    return call


def _apply_call_end(db: Session, business: models.Business, call: models.Call) -> None:
    call.status = "completed"
    call.ended_at = call.ended_at or datetime.now(timezone.utc)
    business.minutes_used = (business.minutes_used or 0) + max(call.duration_seconds // 60, 0)
    if call.customer_id and call.job_id is None:
        latest = (
            db.query(models.Job)
            .filter(
                models.Job.business_id == business.id,
                models.Job.customer_id == call.customer_id,
            )
            .order_by(models.Job.created_at.desc())
            .first()
        )
        if latest:
            call.job_id = latest.id
    db.commit()

    # If nothing was booked and nothing was escalated, make sure the owner
    # still learns about the call. Missed calls are the whole point.
    if call.job_id is None:
        escalated = (
            db.query(models.Message)
            .filter(
                models.Message.business_id == business.id,
                models.Message.template.in_(("escalation", "escalation_emergency")),
                models.Message.created_at >= call.created_at,
            )
            .count()
        )
        if escalated == 0 and call.caller_number:
            messaging.send_to_owner(
                db,
                business,
                f"MISSED CALL — {format_phone(call.caller_number)} called, no job booked. "
                + (f"Summary: {call.summary[:200]}" if call.summary else "No summary available."),
                template="call_followup",
            )


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------
def execute_tool(db: Session, business: models.Business, name: str, args: dict) -> dict:
    if name == "check_availability":
        service_key = args.get("service_key")
        days = int(args.get("days_ahead") or 7)
        days = max(1, min(days, 21))
        agenda = next_open_days(
            business,
            jobs.active_jobs(db, business),
            service_key=service_key,
            days_ahead=days,
            per_day=3,
        )
        if not agenda:
            return {
                "available": False,
                "message": (
                    "No open slots in that window. Offer a callback from the owner "
                    "instead of inventing a time."
                ),
            }
        return {
            "available": True,
            "timezone": timezone_for_province(business.province),
            "days": agenda,
            "message": "Offer at most two options at a time. Read the day and time clearly.",
        }

    if name == "get_service_list":
        return {
            "services": [
                {
                    "key": service.get("key"),
                    "name": service.get("name"),
                    "price_estimate": (
                        f"${service.get('price_min_cents', 0) / 100:.0f}–"
                        f"${service.get('price_max_cents', 0) / 100:.0f}"
                        if service.get("price_max_cents")
                        else "owner confirms"
                    ),
                    "unit": service.get("unit"),
                    "notes": service.get("notes"),
                }
                for service in (business.services or [])
            ],
            "reminder": "Ranges only. The owner confirms the exact price.",
        }

    if name == "book_job":
        try:
            job, warnings = jobs.create_job(
                db,
                business,
                customer_name=args.get("customer_name"),
                customer_phone=args.get("customer_phone"),
                address=args.get("address"),
                service_key=args.get("service_key"),
                service_name=args.get("service_name"),
                preferred_start=args.get("preferred_start"),
                requested_for=args.get("requested_for"),
                notes=args.get("notes"),
                source="voice",
            )
        except jobs.BookingError as exc:
            return {"success": False, "reason": exc.reason, "message": exc.detail}
        return {
            "success": True,
            "job_number": job.number,
            "status": job.status,
            "when": format_local(job.scheduled_start, business)
            if job.scheduled_start
            else job.requested_for or "callback to confirm",
            "warnings": warnings,
            "say_to_caller": (
                f"You're booked for {format_local(job.scheduled_start, business)}. "
                f"We'll text you a confirmation now."
                if job.status == "confirmed"
                else "I've passed this to the owner, who will text you the exact time shortly."
            ),
        }

    if name == "escalate_to_owner":
        urgency = (args.get("urgency") or "normal").lower()
        summary = args.get("summary") or "Caller needs a callback"
        caller_name = args.get("caller_name")
        caller_phone = args.get("caller_phone")
        messaging.send_to_owner(
            db,
            business,
            messaging.tpl_owner_escalation(
                business,
                summary=summary,
                caller_name=caller_name,
                caller_phone=caller_phone,
                urgency=urgency,
            ),
            template="escalation_emergency" if urgency == "emergency" else "escalation",
        )
        return {
            "success": True,
            "notified": True,
            "message": (
                f"{business.owner_name} has been texted immediately."
                if urgency == "emergency"
                else f"{business.owner_name} will call them back."
            ),
        }

    return {"success": False, "error": f"unknown_tool:{name}"}


# ---------------------------------------------------------------------------
# Vapi webhook
# ---------------------------------------------------------------------------
@router.post("/webhooks/vapi")
async def vapi_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: Optional[str] = Header(default=None),
):
    if not verify_vapi_secret(x_vapi_secret):
        raise HTTPException(401, "Bad webhook secret")

    payload = await request.json()
    message = payload.get("message", payload)
    event_type = message.get("type") or payload.get("type") or ""
    business = resolve_business_for_call(db, payload)

    if event_type in ("assistant-request", "assistant_request"):
        if business is None:
            return {"error": "No business is attached to this number yet."}
        return {"assistant": build_assistant_payload(business, settings.base_url)}

    if business is None:
        log.warning("Vapi event for unknown number: %s", event_type)
        return {"ok": True, "ignored": "unknown_number"}

    call = upsert_call(db, business, payload)

    if event_type in ("tool-calls", "tool_calls"):
        call_list = (
            message.get("toolCallList")
            or message.get("toolWithToolCallList")
            or []
        )
        results = []
        for item in call_list:
            tool_call = item.get("toolCall") or item
            call_id = tool_call.get("id") or item.get("id")
            function = tool_call.get("function") or {}
            name = function.get("name") or tool_call.get("name") or ""
            raw_args = function.get("arguments") or tool_call.get("arguments") or {}
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            outcome = execute_tool(db, business, name, raw_args)
            results.append(
                {
                    "toolCallId": call_id,
                    "result": _text(outcome),
                }
            )
            call.tool_calls = (call.tool_calls or []) + [
                {"name": name, "arguments": raw_args, "result": outcome}
            ]
        db.commit()
        if call.job_id is None:
            recent_job = (
                db.query(models.Job)
                .filter(models.Job.business_id == business.id)
                .order_by(models.Job.created_at.desc())
                .first()
            )
            if recent_job and recent_job.created_at >= call.created_at:
                call.job_id = recent_job.id
                db.commit()
        return {"results": results}

    if event_type in ("end-of-call-report", "end_of_call_report"):
        _apply_call_end(db, business, call)
        return {"ok": True, "call_id": call.id}

    if event_type in ("status-update", "status_update"):
        status = message.get("status") or (message.get("call") or {}).get("status")
        if status:
            call.status = "in_progress" if status == "in-progress" else status
            db.commit()
        return {"ok": True}

    return {"ok": True, "ignored": event_type or "unknown"}


# ---------------------------------------------------------------------------
# Bland adapter
# ---------------------------------------------------------------------------
@router.post("/webhooks/bland")
async def bland_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_bland_secret: Optional[str] = Header(default=None),
):
    """Bland posts tool actions and end-of-call reports to one URL as well.

    Set the pathway's webhook URL to this endpoint. Tool actions arrive with an
    `action` / `parameters` shape; everything else is treated as a call report.
    """
    payload = await request.json()
    business = resolve_business_for_call(db, payload)
    if business is None:
        return {"ok": True, "ignored": "unknown_number"}

    action = payload.get("action") or payload.get("tool") or payload.get("function")
    if isinstance(action, dict):
        action = action.get("name")

    if action and action in {
        "check_availability",
        "book_job",
        "escalate_to_owner",
        "get_service_list",
    }:
        args = payload.get("parameters") or payload.get("arguments") or {}
        return execute_tool(db, business, action, args)

    call = upsert_call(db, business, payload)
    if payload.get("transcript") and not call.transcript:
        call.transcript = payload.get("transcript")
    _apply_call_end(db, business, call)
    return {"ok": True, "call_id": call.id}
