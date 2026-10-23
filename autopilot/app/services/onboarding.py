"""Trade presets and business creation.

The pitch is "under five minutes", so onboarding asks for seven things and
derives everything else from the trade preset. Owners can edit the rest later.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from ..phoneutil import normalize_phone
from ..prompt import first_message_for
from ..tax import profile_for_province

TRADE_PRESETS = {
    "snow_removal": {
        "label": "Snow removal",
        "tagline": "Driveways, walkways, and salting",
        "services": [
            {
                "key": "driveway",
                "name": "Driveway clearing",
                "duration_min": 45,
                "price_min_cents": 4500,
                "price_max_cents": 9500,
                "unit": "per visit",
                "rebook_after_days": 0,
                "notes": "double driveway more",
            },
            {
                "key": "walkway",
                "name": "Walkway + steps",
                "duration_min": 25,
                "price_min_cents": 2500,
                "price_max_cents": 4500,
                "unit": "per visit",
                "rebook_after_days": 0,
            },
            {
                "key": "salting",
                "name": "Salting / sanding",
                "duration_min": 20,
                "price_min_cents": 3000,
                "price_max_cents": 6000,
                "unit": "per visit",
                "rebook_after_days": 0,
            },
            {
                "key": "seasonal",
                "name": "Seasonal contract",
                "duration_min": 45,
                "price_min_cents": 35000,
                "price_max_cents": 65000,
                "unit": "per season",
                "rebook_after_days": 300,
                "notes": "based on driveway size",
            },
        ],
        "emergency_keywords": [
            "driveway blocked and they cannot get out",
            "ambulance or fire needs access",
            "roof snow load",
            "frozen pipes",
        ],
        "greeting": None,
        "review_delay_days": 2,
    },
    "lawn_care": {
        "label": "Lawn care & landscaping",
        "tagline": "Mowing, cleanups, and yard work",
        "services": [
            {
                "key": "mowing",
                "name": "Lawn mowing",
                "duration_min": 45,
                "price_min_cents": 4500,
                "price_max_cents": 8000,
                "unit": "per visit",
                "rebook_after_days": 10,
                "notes": "weekly or biweekly",
            },
            {
                "key": "spring_cleanup",
                "name": "Spring cleanup",
                "duration_min": 180,
                "price_min_cents": 25000,
                "price_max_cents": 45000,
                "unit": "per visit",
                "rebook_after_days": 330,
            },
            {
                "key": "fall_cleanup",
                "name": "Fall cleanup / leaves",
                "duration_min": 150,
                "price_min_cents": 22000,
                "price_max_cents": 40000,
                "unit": "per visit",
                "rebook_after_days": 330,
            },
            {
                "key": "hedge",
                "name": "Hedge trimming",
                "duration_min": 90,
                "price_min_cents": 12000,
                "price_max_cents": 25000,
                "unit": "per visit",
                "rebook_after_days": 120,
            },
        ],
        "emergency_keywords": [
            "tree down on the house or driveway",
            "flooding",
            "something dangerous in the yard",
        ],
        "greeting": None,
        "review_delay_days": 2,
    },
    "cleaning": {
        "label": "Residential cleaning",
        "tagline": "Homes, apartments, and move-outs",
        "services": [
            {
                "key": "standard_clean",
                "name": "Standard house cleaning",
                "duration_min": 150,
                "price_min_cents": 14000,
                "price_max_cents": 24000,
                "unit": "per visit",
                "rebook_after_days": 14,
                "notes": "2 bedrooms and up",
            },
            {
                "key": "deep_clean",
                "name": "Deep clean",
                "duration_min": 300,
                "price_min_cents": 28000,
                "price_max_cents": 45000,
                "unit": "per visit",
                "rebook_after_days": 180,
            },
            {
                "key": "move_out",
                "name": "Move-out clean",
                "duration_min": 300,
                "price_min_cents": 30000,
                "price_max_cents": 55000,
                "unit": "per unit",
                "rebook_after_days": 0,
            },
        ],
        "emergency_keywords": [
            "water damage",
            "mold",
            "biohazard or unsafe conditions",
        ],
        "greeting": None,
        "review_delay_days": 2,
    },
    "mobile_grooming": {
        "label": "Mobile grooming",
        "tagline": "Grooming at your door",
        "services": [
            {
                "key": "bath",
                "name": "Bath and brush",
                "duration_min": 60,
                "price_min_cents": 7500,
                "price_max_cents": 11000,
                "unit": "per dog",
                "rebook_after_days": 42,
                "notes": "size dependent",
            },
            {
                "key": "full_groom",
                "name": "Full groom",
                "duration_min": 120,
                "price_min_cents": 11000,
                "price_max_cents": 18000,
                "unit": "per dog",
                "rebook_after_days": 42,
            },
            {
                "key": "nails",
                "name": "Nails and tidy",
                "duration_min": 30,
                "price_min_cents": 3000,
                "price_max_cents": 4500,
                "unit": "per dog",
                "rebook_after_days": 28,
            },
        ],
        "emergency_keywords": [
            "dog is injured or bleeding",
            "heat distress",
            "emergency vet",
        ],
        "greeting": None,
        "review_delay_days": 2,
    },
}

DEFAULT_HOURS = {
    "mon": ["07:00", "18:00"],
    "tue": ["07:00", "18:00"],
    "wed": ["07:00", "18:00"],
    "thu": ["07:00", "18:00"],
    "fri": ["07:00", "18:00"],
    "sat": ["08:00", "16:00"],
    "sun": None,
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "business").lower()).strip("-")
    return slug[:60] or "business"


def unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    counter = 2
    while (
        db.query(models.Business).filter(models.Business.slug == slug).first() is not None
    ):
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def services_for_trade(trade: str) -> list[dict]:
    preset = TRADE_PRESETS.get(trade) or TRADE_PRESETS["snow_removal"]
    return [dict(service) for service in preset["services"]]


def create_business(
    db: Session,
    *,
    name: str,
    owner_name: str,
    owner_phone: str,
    trade: str = "snow_removal",
    city: Optional[str] = None,
    province: str = "QC",
    service_area: Optional[str] = None,
    phone_number: Optional[str] = None,
    owner_email: Optional[str] = None,
    hours: Optional[dict] = None,
    services: Optional[list] = None,
    review_url: Optional[str] = None,
    etransfer_email: Optional[str] = None,
    greeting: Optional[str] = None,
    hst_enabled: bool = True,
    tax_profile: Optional[str] = None,
    tax_number: Optional[str] = None,
    plan: str = "trial",
) -> models.Business:
    preset = TRADE_PRESETS.get(trade) or TRADE_PRESETS["snow_removal"]
    business = models.Business(
        slug=unique_slug(db, name),
        name=name.strip(),
        trade=trade if trade in TRADE_PRESETS else "snow_removal",
        owner_name=owner_name.strip(),
        owner_phone=normalize_phone(owner_phone) or owner_phone,
        owner_email=owner_email,
        city=city,
        province=(province or "QC").upper()[:2],
        service_area=service_area or (f"{city} and surrounding area" if city else None),
        phone_number=normalize_phone(phone_number) if phone_number else None,
        hours=hours or DEFAULT_HOURS,
        services=services or services_for_trade(trade),
        after_hours={"mode": "callback", "accepts_etransfer": True, "text_owner": True},
        emergency_keywords=preset["emergency_keywords"],
        greeting=greeting,
        review_url=review_url,
        review_delay_days=preset["review_delay_days"],
        etransfer_email=etransfer_email,
        tax_profile=tax_profile or profile_for_province(province),
        hst_enabled=hst_enabled,
        tax_number=tax_number,
        plan=plan,
        plan_status="trialing" if plan == "trial" else "active",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14)
        if plan == "trial"
        else None,
        minutes_included=200,
    )
    if not business.greeting:
        business.greeting = first_message_for(business)
    db.add(business)
    db.commit()
    db.refresh(business)
    return business


# ---------------------------------------------------------------------------
# Guided text onboarding
# ---------------------------------------------------------------------------
ONBOARDING_STEPS = [
    ("trade", "What's your trade? Reply 1 snow removal, 2 lawn care, 3 cleaning, 4 mobile grooming."),
    ("name", "What's your business name?"),
    ("owner", "And your first name?"),
    ("city", "What town do you work in?"),
    ("area", "Which areas or postal codes do you cover? (e.g. Beauce, G6V)"),
    ("services", "Anything you don't offer? Reply ALL, or list what to remove (e.g. 'no salting')."),
    ("review", "Paste your Google review link, or reply SKIP."),
]

TRADE_ALIASES = {
    "1": "snow_removal",
    "snow": "snow_removal",
    "snow removal": "snow_removal",
    "deneigement": "snow_removal",
    "2": "lawn_care",
    "lawn": "lawn_care",
    "lawn care": "lawn_care",
    "3": "cleaning",
    "cleaning": "cleaning",
    "house cleaning": "cleaning",
    "4": "mobile_grooming",
    "grooming": "mobile_grooming",
    "mobile grooming": "mobile_grooming",
}


def next_question(step: str) -> str:
    for key, prompt in ONBOARDING_STEPS:
        if key == step:
            return prompt
    return "Thanks! We'll text you a login link shortly."


def start_text_onboarding(db: Session, phone: str) -> tuple[models.OnboardingDraft, str]:
    normalized = normalize_phone(phone) or phone
    draft = (
        db.query(models.OnboardingDraft)
        .filter(models.OnboardingDraft.phone == normalized)
        .order_by(models.OnboardingDraft.created_at.desc())
        .first()
    )
    if draft is None or draft.step == "done":
        draft = models.OnboardingDraft(phone=normalized, step="trade", data={})
        db.add(draft)
        db.commit()
        db.refresh(draft)
    return draft, next_question(draft.step)


def advance_text_onboarding(db: Session, draft: models.OnboardingDraft, body: str) -> dict:
    """Consume one answer. Returns {reply, business_created, business}."""
    text = body.strip()
    data = dict(draft.data or {})

    if draft.step == "trade":
        trade = TRADE_ALIASES.get(text.lower().strip(), "snow_removal")
        data["trade"] = trade
        draft.step = "name"
    elif draft.step == "name":
        data["name"] = text[:120]
        draft.step = "owner"
    elif draft.step == "owner":
        data["owner_name"] = text[:80]
        draft.step = "city"
    elif draft.step == "city":
        data["city"] = text[:100]
        draft.step = "area"
    elif draft.step == "area":
        data["service_area"] = text[:240]
        draft.step = "services"
    elif draft.step == "services":
        excluded = text.lower()
        services = services_for_trade(data.get("trade", "snow_removal"))
        if "no salting" in excluded or "pas de sel" in excluded:
            services = [s for s in services if s["key"] != "salting"]
        data["services"] = services
        draft.step = "review"
    elif draft.step == "review":
        if text.lower() not in ("skip", "no", "none"):
            data["review_url"] = text[:400]
        draft.step = "done"
    else:
        draft.step = "done"

    draft.data = data
    db.commit()

    if draft.step != "done":
        return {"reply": next_question(draft.step), "business_created": False, "business": None}

    business = create_business(
        db,
        name=data.get("name") or "My business",
        owner_name=data.get("owner_name") or "Owner",
        owner_phone=draft.phone,
        trade=data.get("trade", "snow_removal"),
        city=data.get("city"),
        service_area=data.get("service_area"),
        services=data.get("services"),
        review_url=data.get("review_url"),
    )
    return {
        "reply": (
            f"You're set, {business.owner_name}! Your line is {business.phone_number or 'being assigned'}. "
            f"Text TODAY anytime to see your schedule. Reply HELP for commands."
        ),
        "business_created": True,
        "business": business,
    }
