"""SMS transport. Twilio in production, dry-run ledger otherwise."""
import logging
from typing import Optional

import httpx

from ..config import settings

log = logging.getLogger("autopilot.sms")


class SmsResult:
    def __init__(self, sid: Optional[str], status: str, error: Optional[str] = None):
        self.sid = sid
        self.status = status
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None


def send_sms(to_number: str, body: str, from_number: Optional[str] = None) -> SmsResult:
    """Send one SMS. Never raises — a texting failure must not break a booking."""
    if not to_number:
        return SmsResult(None, "failed", "missing destination")

    sender = from_number or settings.twilio_from_number
    if settings.sms_dry_run or not sender:
        log.info("[dry-run SMS] to=%s body=%s", to_number, body)
        return SmsResult(None, "dry_run")

    try:
        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            data={"To": to_number, "From": sender, "Body": body},
            timeout=15,
        )
    except httpx.HTTPError as exc:  # network failure
        log.warning("Twilio send failed: %s", exc)
        return SmsResult(None, "failed", str(exc))

    if response.status_code >= 300:
        log.warning("Twilio error %s: %s", response.status_code, response.text[:300])
        return SmsResult(None, "failed", response.text[:300])

    payload = response.json()
    return SmsResult(payload.get("sid"), payload.get("status", "queued"))
