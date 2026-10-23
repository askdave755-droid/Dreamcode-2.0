"""The master voice-agent prompt.

One template, rendered from a business profile. The guardrails are deliberate:
the agent must disclose it is an AI, must not invent firm prices, must hand off
anything unusual to the owner, and must capture the five fields we need to book
and invoice a job.
"""
import json
from typing import Optional

from .models import Business

MASTER_PROMPT = """\
# ROLE
You are {agent_name}, the phone assistant for {business_name}, a {trade_label} \
business serving {service_area} ({province}). You answer calls the owner \
{safe_owner_name} cannot pick up. You are warm, brief, and practical — the \
caller is usually standing in a driveway or on a ladder.

# WHO YOU ARE (MANDATORY DISCLOSURE)
Open by saying you are {business_name}'s AI assistant. Never claim to be a \
human, never claim to be the owner, and never deny being an AI if asked. If the \
caller asks for a person, offer to have {safe_owner_name} call them back and \
collect the details for that callback.

# THE BUSINESS
- Trade: {trade_label}
- Hours: {hours_text}
- Service area: {service_area}
- Services and typical price ranges:
{services_text}
- Payment: {payment_text}
- Timezone: {timezone}

# YOUR JOB, IN ORDER
1. Find out what they need, and for which property address.
2. Capture: full name, mobile number, service address, the service needed, and \
when they want it. Read the phone number and address back to confirm.
3. Give a rough range from the list above, clearly labelled as an estimate: \
"typically between $X and $Y, and the owner confirms the exact price." Never \
quote a firm price, never invent a range that is not listed, and never discount.
4. Offer the open slots you get from check_availability. If none fit, offer the \
next available day, or promise a callback from {safe_owner_name} — the owner \
confirms exact timing.
5. When the caller agrees, call book_job with everything you collected. Then \
confirm out loud that the job is on the schedule and that a text message will \
follow.
6. If the caller needs something outside the list, is upset, is a commercial \
account, or asks for a firm quote on a large job, call escalate_to_owner and \
tell the caller {safe_owner_name} will call them shortly.

# EMERGENCIES — DO NOT BOOK, ESCALATE
These are emergencies: {emergency_text}
For an emergency, say: "I'm sending this to {safe_owner_name} right now as an \
urgent message. If you don't hear back within 30 minutes, call {owner_phone}." \
Then call escalate_to_owner with urgency="emergency". Do not promise an arrival \
time.

# RULES THAT ARE NOT NEGOTIABLE
- Never promise a specific arrival time. Give a slot or a callback.
- Never take credit card numbers, SINs, or any payment details on the call.
  Payment is by {payment_text}.
- Never say a job is confirmed unless book_job returned success=true.
- Never give legal, insurance, or warranty advice.
- If the caller is not in the service area, say so and offer to pass the message
  to the owner instead of booking.
- Keep answers short: two sentences, then ask the next question.
- If the caller speaks French, continue in French. {language_line}
- If you don't know, say so and call escalate_to_owner.

# TONE
{tone_line} Use plain language. No jargon, no corporate filler. Never argue with \
a caller. If they are frustrated, acknowledge it in one sentence and move to a fix.

# OPENING LINE
{first_message}
"""


def _money(cents: Optional[int]) -> str:
    if cents is None:
        return "call for price"
    return f"${cents / 100:,.0f}"


def _hours_text(hours: dict) -> str:
    labels = {
        "mon": "Mon",
        "tue": "Tue",
        "wed": "Wed",
        "thu": "Thu",
        "fri": "Fri",
        "sat": "Sat",
        "sun": "Sun",
    }
    if not hours:
        return "Monday to Saturday, 7am to 7pm"
    chunks = []
    for key in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        window = hours.get(key)
        if not window or len(window) != 2:
            chunks.append(f"{labels[key]} closed")
        else:
            chunks.append(f"{labels[key]} {window[0]}–{window[1]}")
    return ", ".join(chunks)


def _services_text(services: list) -> str:
    if not services:
        return "  - General service — owner confirms pricing"
    lines = []
    for service in services:
        low = service.get("price_min_cents")
        high = service.get("price_max_cents")
        unit = service.get("unit") or "per visit"
        if low and high:
            price = f"{_money(low)}–{_money(high)} {unit}"
        elif low:
            price = f"from {_money(low)} {unit}"
        else:
            price = "price confirmed by owner"
        note = f" ({service['notes']})" if service.get("notes") else ""
        lines.append(f"  - {service.get('name')}: {price}{note}")
    return "\n".join(lines)


def _payment_text(business: Business) -> str:
    pieces = ["card payment link by text"]
    if (business.after_hours or {}).get("accepts_etransfer", True):
        pieces.append("Interac e-Transfer")
    return " or ".join(pieces)


def _tone_line(tone: Optional[str]) -> str:
    return {
        "friendly": "Be friendly and informal, like a neighbour who knows the trade.",
        "professional": "Be courteous and precise, like a well-run local company.",
        "direct": "Be brisk and no-nonsense. Respect their time.",
    }.get((tone or "friendly").lower(), "Be friendly and clear.")


def _language_line(language: Optional[str]) -> str:
    return {
        "fr": "Start in French; switch to English only if the caller does.",
        "bilingual": "Match the caller's language — French or English — from their first sentence.",
        "en": "Default to English; switch to French if the caller does.",
    }.get((language or "en").lower(), "Default to English.")


def first_message_for(business: Business) -> str:
    greeting = (business.greeting or "").strip()
    if greeting:
        return greeting
    trade = (business.trade or "service").replace("_", " ")
    return (
        f"Hi, you've reached {business.name} — this is their AI assistant. "
        f"Are you calling about {trade}, or something else?"
    )


def build_system_prompt(business: Business, timezone: Optional[str] = None) -> str:
    """Render the master prompt for one business."""
    services = business.services or []
    trade_label = (business.trade or "service").replace("_", " ").title()
    emergency_keywords = business.emergency_keywords or []
    emergency_text = (
        ", ".join(emergency_keywords)
        if emergency_keywords
        else "burst pipe, no heat, collapsed roof, someone is hurt, or the driveway is blocked and they cannot get out"
    )
    return MASTER_PROMPT.format(
        agent_name=f"{business.owner_name.split()[0]}'s assistant"
        if business.owner_name
        else "the assistant",
        business_name=business.name,
        trade_label=trade_label,
        safe_owner_name=business.owner_name,
        owner_phone=business.owner_phone,
        service_area=business.service_area or business.city or "the local area",
        province=business.province,
        hours_text=_hours_text(business.hours or {}),
        services_text=_services_text(services),
        payment_text=_payment_text(business),
        timezone=timezone or "America/Toronto",
        emergency_text=emergency_text,
        language_line=_language_line(business.language),
        tone_line=_tone_line(business.tone),
        first_message=first_message_for(business),
    )


def build_knowledge_snapshot(business: Business) -> str:
    """Compact JSON handed to the model as structured context."""
    return json.dumps(
        {
            "business": business.name,
            "trade": business.trade,
            "timezone": timezone_or_default(business),
            "hours": business.hours or {},
            "services": business.services or [],
            "service_area": business.service_area,
            "postal_codes": business.postal_codes or [],
        },
        separators=(",", ":"),
    )


def timezone_or_default(business: Business) -> str:
    from .tax import timezone_for_province

    return timezone_for_province(business.province)
