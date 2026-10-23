"""Pure unit tests: money and time logic."""
from datetime import date, datetime, timedelta

from zoneinfo import ZoneInfo

from app import models
from app.availability import (
    DAY_KEYS,
    format_local,
    next_open_days,
    open_slots,
    parse_datetime_loose,
    slot_is_available,
)
from app.services.billing import next_invoice_number
from app.tax import compute_tax

TZ = ZoneInfo("America/Toronto")


def test_quebec_tax_is_gst_plus_qst():
    result = compute_tax(10000, "qc_gst_qst")
    assert result.subtotal_cents == 10000
    assert result.tax_cents == 500 + 998  # 5% + 9.975%, rounded
    assert result.total_cents == 11498
    labels = [component["label"] for component in result.breakdown]
    assert labels == ["GST", "QST"]


def test_ontario_hst_and_nova_scotia_rate():
    assert compute_tax(10000, "on_hst").tax_cents == 1300
    assert compute_tax(10000, "ns_hst").tax_cents == 1400
    assert compute_tax(10000, "ab_gst").tax_cents == 500


def test_tax_can_be_disabled_for_unregistered_business():
    result = compute_tax(5000, "qc_gst_qst", enabled=False)
    assert result.tax_cents == 0
    assert result.total_cents == 5000


def test_tax_rounds_to_the_cent_not_the_dollar():
    result = compute_tax(4599, "qc_gst_qst")
    assert result.tax_cents == 230 + 459  # 229.95 -> 230, 458.75 -> 459
    assert result.total_cents == 4599 + 689


def test_slots_respect_business_hours_and_duration(business):
    business.hours = {day: ["08:00", "12:00"] for day in DAY_KEYS}
    target = date.today() + timedelta(days=3)
    # Skip days the business is closed in case the test runs on Sunday.
    while business.hours.get(DAY_KEYS[target.weekday()]) is None:
        target += timedelta(days=1)

    slots = open_slots(business, target, [], service_key="driveway", limit=20)
    assert slots, "expected slots inside opening hours"
    assert all(slot.hour >= 8 for slot in slots)
    # A 45-minute service starting at 11:30 would run past 12:00.
    assert all(slot.hour < 12 for slot in slots)
    assert slots[-1].strftime("%H:%M") <= "11:15"


def test_booked_job_blocks_the_slot(business):
    business.hours = {day: ["08:00", "18:00"] for day in DAY_KEYS}
    day = date.today() + timedelta(days=2)
    while not business.hours.get(DAY_KEYS[day.weekday()]):
        day += timedelta(days=1)
    start = datetime.combine(day, datetime.min.time(), tzinfo=TZ).replace(hour=10)
    job = models.Job(
        business_id=business.id,
        number=99,
        service_key="driveway",
        service_name="Driveway clearing",
        status="confirmed",
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=45),
    )
    ok, reason = slot_is_available(business, start, "driveway", [job])
    assert not ok
    assert reason == "slot_taken"

    later = start.replace(hour=14)
    ok, _ = slot_is_available(business, later, "driveway", [job])
    assert ok


def test_closed_day_is_not_bookable(business):
    business.hours = {"mon": ["08:00", "18:00"]}
    monday = date(2026, 11, 2)  # a Monday
    slot = datetime(2026, 11, 3, 10, 0, tzinfo=TZ)  # Tuesday
    ok, reason = slot_is_available(business, slot, "driveway", [])
    assert not ok
    assert reason == "closed_that_day"
    assert monday.weekday() == 0


def test_parse_loose_time_strings(business):
    parsed = parse_datetime_loose("tomorrow 9am", business)
    assert parsed is not None and parsed.hour == 9
    assert parse_datetime_loose("2026-11-12T13:30", business).hour == 13
    assert parse_datetime_loose("not a time", business) is None


def test_next_open_days_returns_labels(business):
    agenda = next_open_days(business, [], days_ahead=5, per_day=2)
    assert agenda
    assert all("label" in day and day["slots"] for day in agenda)


def test_invoice_numbers_increase_per_business(db, business):
    first = next_invoice_number(db, business)
    assert first == "INV-1001"


def test_format_local_uses_business_timezone(business):
    utc = datetime(2026, 1, 15, 14, 0, tzinfo=ZoneInfo("UTC"))
    assert "9:00" in format_local(utc, business).replace("AM", "")


def test_parse_weekday_and_month_expressions(business):
    friday = parse_datetime_loose("Fri 9am", business)
    assert friday is not None and friday.hour == 9 and friday.weekday() == 4
    # A weekday already passed (or later today) rolls forward a week.
    assert friday >= parse_datetime_loose("today 00:01", business)

    november = parse_datetime_loose("12 nov 13:00", business)
    assert november is not None
    assert (november.month, november.day, november.hour) == (11, 12, 13)
