"""Phone number normalization.

Canadian/NANP focus: a bare 10-digit number becomes +1XXXXXXXXXX so the same
customer cannot be created twice with two spellings.
"""
import re
from typing import Optional

NANP = re.compile(r"^\+1(\d{3})(\d{3})(\d{4})$")


def normalize_phone(raw: Optional[str], default_country: str = "1") -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 10:
        digits = default_country + digits
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.strip().startswith("+") and digits:
        return f"+{digits}"
    return None


def format_phone(raw: Optional[str]) -> str:
    normalized = normalize_phone(raw)
    if not normalized:
        return raw or "unknown"
    match = NANP.match(normalized)
    if match:
        return f"({match.group(1)}) {match.group(2)}-{match.group(3)}"
    return normalized


def is_canadian(raw: Optional[str]) -> bool:
    normalized = normalize_phone(raw)
    return bool(normalized and NANP.match(normalized))
