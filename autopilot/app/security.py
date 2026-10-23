"""Auth primitives: owner session cookies, OTP codes, webhook signatures."""
import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional

from .config import settings

COOKIE_NAME = "autopilot_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: str) -> str:
    mac = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256)
    return _b64(mac.digest())


def make_session_token(business_id: str) -> str:
    payload = f"{business_id}:{int(time.time())}"
    return f"{_b64(payload.encode())}.{_sign(payload)}"


def read_session_token(token: Optional[str]) -> Optional[str]:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    try:
        payload = _unb64(encoded).decode()
    except Exception:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    business_id, _, issued = payload.rpartition(":")
    if not business_id:
        return None
    try:
        if int(time.time()) - int(issued) > SESSION_MAX_AGE:
            return None
    except ValueError:
        return None
    return business_id


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hmac.new(
        settings.secret_key.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def verify_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)


def verify_twilio_signature(url: str, params: dict, signature: Optional[str]) -> bool:
    """Validate X-Twilio-Signature (HMAC-SHA1 over URL + sorted params)."""
    if not settings.verify_twilio_signature or not settings.twilio_auth_token:
        return True
    if not signature:
        return False
    payload = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(
        settings.twilio_auth_token.encode(), payload.encode(), hashlib.sha1
    ).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def verify_vapi_secret(header_value: Optional[str]) -> bool:
    if not settings.vapi_webhook_secret:
        return True
    return bool(header_value) and hmac.compare_digest(
        header_value or "", settings.vapi_webhook_secret
    )


def verify_cron_secret(provided: Optional[str], authorization: Optional[str] = None) -> bool:
    if not settings.cron_secret:
        return True
    if provided and hmac.compare_digest(provided, settings.cron_secret):
        return True
    if authorization and authorization.startswith("Bearer "):
        return hmac.compare_digest(authorization[7:], settings.cron_secret)
    return False
