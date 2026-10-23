"""Availability: simple, defensible rules over the jobs table.

We do not need a real calendar engine for a one-van trade business. A slot is
open when it sits inside business hours, fits the service duration, and does
not overlap a live job (plus a travel buffer).
"""
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from . import models
from .tax import timezone_for_province

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SLOT_STEP_MIN = 30
TRAVEL_BUFFER_MIN = 15
ACTIVE_STATUSES = ("confirmed", "requested", "needs_confirmation", "in_progress")


def business_tz(business: models.Business) -> ZoneInfo:
    return ZoneInfo(timezone_for_province(business.province))


def local_now(business: models.Business) -> datetime:
    return datetime.now(business_tz(business))


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: Optional[datetime], business: models.Business) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(business_tz(business))


def _parse_hhmm(value: str) -> Optional[time]:
    try:
        hour, minute = value.split(":")[:2]
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


def service_duration_minutes(business: models.Business, service_key: str) -> int:
    for service in business.services or []:
        if service.get("key") == service_key:
            return int(service.get("duration_min") or 60)
    return 60


def _day_window(business: models.Business, day: date) -> Optional[tuple[time, time]]:
    hours = business.hours or {}
    window = hours.get(DAY_KEYS[day.weekday()])
    if not window or len(window) != 2:
        return None
    opens, closes = _parse_hhmm(window[0]), _parse_hhmm(window[1])
    if not opens or not closes or closes <= opens:
        return None
    return opens, closes


def _job_intervals(business: models.Business, jobs: Iterable[models.Job], day: date):
    intervals = []
    for job in jobs:
        if job.scheduled_start is None or job.status not in ACTIVE_STATUSES:
            continue
        start = to_local(job.scheduled_start, business)
        end = to_local(job.scheduled_end, business) or start
        if start.date() != day and end.date() != day:
            continue
        intervals.append(
            (
                start - timedelta(minutes=TRAVEL_BUFFER_MIN),
                end + timedelta(minutes=TRAVEL_BUFFER_MIN),
            )
        )
    return intervals


def open_slots(
    business: models.Business,
    day: date,
    jobs: Iterable[models.Job],
    service_key: Optional[str] = None,
    limit: int = 6,
    not_before: Optional[datetime] = None,
) -> list[datetime]:
    """Return open local start times for one day."""
    window = _day_window(business, day)
    if not window:
        return []
    tz = business_tz(business)
    opens, closes = window
    duration = timedelta(minutes=service_duration_minutes(business, service_key or ""))
    intervals = _job_intervals(business, jobs, day)
    earliest = not_before or local_now(business)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=tz)

    cursor = datetime.combine(day, opens, tzinfo=tz)
    day_close = datetime.combine(day, closes, tzinfo=tz)
    slots: list[datetime] = []
    while cursor + duration <= day_close and len(slots) < limit:
        slot_end = cursor + duration
        busy = any(cursor < end and slot_end > start for start, end in intervals)
        if not busy and cursor >= earliest + timedelta(minutes=30):
            slots.append(cursor)
        cursor += timedelta(minutes=SLOT_STEP_MIN)
    return slots


def next_open_days(
    business: models.Business,
    jobs: Iterable[models.Job],
    service_key: Optional[str] = None,
    days_ahead: int = 7,
    per_day: int = 3,
) -> list[dict]:
    """Human-friendly agenda: [{date, label, slots:[iso...]}]."""
    jobs = list(jobs)
    today = local_now(business).date()
    results = []
    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        slots = open_slots(business, day, jobs, service_key, limit=per_day)
        if slots:
            results.append(
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%a %b %d"),
                    "slots": [slot.isoformat() for slot in slots],
                }
            )
    return results


def slot_is_available(
    business: models.Business,
    start: datetime,
    service_key: str,
    jobs: Iterable[models.Job],
) -> tuple[bool, str]:
    """Check one proposed start time. Returns (ok, reason)."""
    tz = business_tz(business)
    if start.tzinfo is None:
        start = start.replace(tzinfo=tz)
    local = start.astimezone(tz)
    window = _day_window(business, local.date())
    if not window:
        return False, "closed_that_day"
    opens, closes = window
    duration = timedelta(minutes=service_duration_minutes(business, service_key))
    end = local + duration
    if local.time() < opens or end.time() > closes or end.date() != local.date():
        return False, "outside_business_hours"
    if local < local_now(business) + timedelta(minutes=30):
        return False, "too_soon"
    for busy_start, busy_end in _job_intervals(business, jobs, local.date()):
        if local < busy_end and end > busy_start:
            return False, "slot_taken"
    return True, "ok"


WEEKDAYS = {
    "mon": 0, "monday": 0, "lun": 0, "lundi": 0,
    "tue": 1, "tues": 1, "tuesday": 1, "mar": 1, "mardi": 1,
    "wed": 2, "weds": 2, "wednesday": 2, "mer": 2, "mercredi": 2,
    "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "jeu": 3, "jeudi": 3,
    "fri": 4, "friday": 4, "ven": 4, "vendredi": 4,
    "sat": 5, "saturday": 5, "sam": 5, "samedi": 5,
    "sun": 6, "sunday": 6, "dim": 6, "dimanche": 6,
}

MONTHS = {
    "jan": 1, "january": 1, "janvier": 1,
    "feb": 2, "february": 2, "fevrier": 2, "février": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juillet": 7,
    "aug": 8, "august": 8, "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "decembre": 12, "décembre": 12,
}


def parse_datetime_loose(value: str, business: models.Business) -> Optional[datetime]:
    """Parse what people actually type: 'tomorrow 9am', 'Fri 9am', 'Nov 12 1pm'.

    Returns a timezone-aware datetime in the business's timezone, or None.
    """
    if not value:
        return None
    tz = business_tz(business)
    text = value.strip()
    lowered = text.lower()

    if lowered.startswith("today") or lowered.startswith("tomorrow"):
        base = local_now(business)
        day = base.date() + (
            timedelta(days=1) if lowered.startswith("tomorrow") else timedelta(0)
        )
        parsed_time = _parse_clock(text.split(" ", 1)[1] if " " in text else "")
        if parsed_time:
            return datetime.combine(day, parsed_time, tzinfo=tz)

    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except ValueError:
        pass

    now = local_now(business)
    tokens = re.findall(r"[a-zéûôà]+|\d{1,2}:\d{2}|\d{1,2}", lowered)

    candidate_day = None
    weekday = next((WEEKDAYS[t] for t in tokens if t in WEEKDAYS), None)
    month = next((MONTHS[t] for t in tokens if t in MONTHS), None)

    if "tomorrow" in tokens or "demain" in lowered:
        candidate_day = now.date() + timedelta(days=1)
    elif "today" in tokens or "aujourd" in lowered:
        candidate_day = now.date()
    elif weekday is not None:
        delta = (weekday - now.weekday()) % 7
        candidate_day = now.date() + timedelta(days=delta)
    elif month is not None:
        day_number = next(
            (
                int(token)
                for token in tokens
                if token.isdigit() and 1 <= int(token) <= 31
            ),
            None,
        )
        if day_number:
            year = now.year
            try:
                candidate_day = date(year, month, day_number)
            except ValueError:
                return None
            if candidate_day < now.date():
                candidate_day = date(year + 1, month, day_number)

    parsed_time = None
    clock_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", lowered)
    if clock_match:
        parsed_time = _parse_clock(clock_match.group(0))
    if parsed_time is None:
        military = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
        if military:
            parsed_time = time(int(military.group(1)), int(military.group(2)))

    if candidate_day is None:
        return None
    if parsed_time is None:
        window = _day_window(business, candidate_day)
        parsed_time = window[0] if window else time(9, 0)

    result = datetime.combine(candidate_day, parsed_time, tzinfo=tz)
    # "Friday 9am" said on a Friday afternoon means next Friday.
    if weekday is not None and result <= now:
        result += timedelta(days=7)
    return result


def _parse_clock(text: str) -> Optional[time]:
    text = (text or "").strip().lower().replace(".", "")
    for fmt in ("%I:%M%p", "%I%p", "%H:%M", "%H"):
        try:
            return datetime.strptime(text.replace(" ", ""), fmt).time()
        except ValueError:
            continue
    return None


def format_local(dt: Optional[datetime], business: models.Business, with_time: bool = True) -> str:
    local = to_local(dt, business)
    if local is None:
        return "not scheduled"
    return local.strftime("%a %b %d at %-I:%M %p") if with_time else local.strftime("%a %b %d")
