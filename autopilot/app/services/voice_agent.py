"""Voice agent definition and provisioning.

The assistant is described once, here, as plain JSON. That means switching
between Vapi and Bland (or moving to Retell later) is a payload change, not a
rewrite — the webhook contract stays the same.
"""
import logging
import httpx

from .. import models
from ..config import settings
from ..prompt import build_system_prompt, first_message_for
from ..tax import timezone_for_province

log = logging.getLogger("autopilot.voice")

VAPI_API = "https://api.vapi.ai"

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Look up open appointment slots. Call this before offering any time. "
                "If nothing is open, offer a callback instead of inventing a slot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service_key": {
                        "type": "string",
                        "description": "Service key from the service list, e.g. driveway.",
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days to look ahead. Default 7.",
                    },
                    "preferred_day": {
                        "type": "string",
                        "description": "Optional ISO date the caller asked about.",
                    },
                },
                "required": ["service_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_job",
            "description": (
                "Book the job after the caller agrees to a slot. Only call once you "
                "have name, phone, address, service and a slot or requested time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "customer_phone": {
                        "type": "string",
                        "description": "E.164 or 10-digit Canadian number.",
                    },
                    "address": {"type": "string"},
                    "service_key": {"type": "string"},
                    "preferred_start": {
                        "type": "string",
                        "description": "ISO 8601 slot returned by check_availability.",
                    },
                    "requested_for": {
                        "type": "string",
                        "description": "Free-text timing if no slot was agreed.",
                    },
                    "notes": {"type": "string"},
                },
                "required": ["customer_name", "customer_phone", "service_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_owner",
            "description": (
                "Text the owner a callback request. Use for emergencies, unusual "
                "requests, commercial work, firm quotes, or an upset caller."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "One or two sentences: who, what, where, when.",
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["normal", "emergency"],
                    },
                    "caller_name": {"type": "string"},
                    "caller_phone": {"type": "string"},
                },
                "required": ["summary", "urgency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_service_list",
            "description": "Return services with rough price ranges. Never quote outside these.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def build_assistant_payload(business: models.Business, base_url: str) -> dict:
    """The full Vapi assistant definition for one tenant."""
    server_url = f"{base_url.rstrip('/')}/webhooks/vapi"
    return {
        "name": f"{business.name} — receptionist",
        "firstMessage": business.greeting or first_message_for(business),
        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": build_system_prompt(business)},
            ],
            "tools": TOOL_DEFINITIONS,
        },
        "voice": {
            "provider": "11labs",
            "voiceId": "paula" if business.language == "fr" else "elliot",
        },
        "transcriber": {"provider": "deepgram", "language": "fr" if business.language == "fr" else "en"},
        "serverUrl": server_url,
        "serverUrlSecret": settings.vapi_webhook_secret,
        "serverMessages": [
            "tool-calls",
            "end-of-call-report",
            "status-update",
        ],
        "metadata": {"business_id": business.id, "trade": business.trade},
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 600,
        "endCallMessage": "Thanks for calling. We'll text you a confirmation shortly.",
        "recordingEnabled": True,
        "analysisPlan": {
            "summaryPrompt": (
                "Summarize this call in two sentences: what the caller wanted, "
                "the address, and whether a job was booked or the owner must call back. "
                "Flag any emergency in capitals."
            )
        },
    }


def provision_assistant(business: models.Business, base_url: str) -> dict:
    """Create or update the assistant in Vapi. Dry-run returns the payload."""
    payload = build_assistant_payload(business, base_url)
    if not settings.vapi_api_key:
        return {
            "provisioned": False,
            "mode": "dry_run",
            "reason": "VAPI_API_KEY not configured",
            "payload": payload,
        }

    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    try:
        if business.vapi_assistant_id:
            response = httpx.patch(
                f"{VAPI_API}/assistant/{business.vapi_assistant_id}",
                json=payload,
                headers=headers,
                timeout=30,
            )
        else:
            response = httpx.post(
                f"{VAPI_API}/assistant", json=payload, headers=headers, timeout=30
            )
    except httpx.HTTPError as exc:
        return {"provisioned": False, "mode": "error", "reason": str(exc), "payload": payload}

    if response.status_code >= 300:
        return {
            "provisioned": False,
            "mode": "error",
            "reason": f"{response.status_code}: {response.text[:300]}",
            "payload": payload,
        }
    data = response.json()
    business.vapi_assistant_id = data.get("id")
    return {"provisioned": True, "mode": "live", "assistant": data, "payload": payload}


def timezone_label(business: models.Business) -> str:
    return timezone_for_province(business.province)
