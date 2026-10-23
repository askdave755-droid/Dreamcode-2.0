"""Domain model for the trades admin autopilot.

Tenancy rule: every tenant-owned table carries `business_id` and every query
in the app filters on it. There is no cross-tenant lookup helper on purpose.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UTCDateTime(TypeDecorator):
    """Timezone-aware timestamps that behave the same on Postgres and SQLite.

    SQLite has no tz-aware type: a plain DateTime column silently drops the
    offset, which shifts bookings by the UTC delta. This stores UTC and always
    hands back an aware datetime.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at = Column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------
class Business(Base, TimestampMixin):
    __tablename__ = "businesses"

    id = Column(String(36), primary_key=True, default=new_id)
    slug = Column(String(80), unique=True, nullable=False, index=True)

    # Identity / profile
    name = Column(String(160), nullable=False)
    trade = Column(String(40), nullable=False, default="snow_removal")
    owner_name = Column(String(120), nullable=False)
    owner_phone = Column(String(24), nullable=False, index=True)  # E.164
    owner_email = Column(String(160), nullable=True)
    city = Column(String(120), nullable=True)
    province = Column(String(2), nullable=False, default="QC")
    service_area = Column(Text, nullable=True)
    postal_codes = Column(JSON, default=list)

    # Telephony
    phone_number = Column(String(24), nullable=True, index=True)  # dedicated line
    vapi_assistant_id = Column(String(80), nullable=True)

    # Voice persona
    greeting = Column(Text, nullable=True)
    tone = Column(String(24), default="friendly")
    language = Column(String(8), default="en")
    hours = Column(JSON, default=dict)  # {"mon": ["08:00", "18:00"], ...}
    after_hours = Column(JSON, default=dict)  # {"mode": "callback"|"escalate"}
    emergency_keywords = Column(JSON, default=list)
    transfer_number = Column(String(24), nullable=True)

    # Catalogue: [{key, name, duration_min, price_min_cents, price_max_cents,
    #              unit, rebook_after_days, notes}]
    services = Column(JSON, default=list)

    # Money & tax
    currency = Column(String(3), default="CAD", nullable=False)
    tax_profile = Column(String(16), default="qc_gst_qst", nullable=False)
    hst_enabled = Column(Boolean, default=True, nullable=False)
    tax_number = Column(String(40), nullable=True)  # GST/QST registration
    etransfer_email = Column(String(160), nullable=True)

    # Customer lifecycle automation
    review_url = Column(String(400), nullable=True)
    review_delay_days = Column(Integer, default=2)
    rebook_enabled = Column(Boolean, default=True)
    sms_footer = Column(String(200), default="Reply STOP to opt out.")

    # Billing of the business itself
    plan = Column(String(24), default="trial", nullable=False)
    plan_status = Column(String(24), default="trialing", nullable=False)
    trial_ends_at = Column(UTCDateTime(), nullable=True)
    stripe_customer_id = Column(String(80), nullable=True)
    stripe_subscription_id = Column(String(80), nullable=True)
    minutes_included = Column(Integer, default=0)
    minutes_used = Column(Integer, default=0)
    paused = Column(Boolean, default=False, nullable=False)

    customers = relationship("Customer", back_populates="business")
    jobs = relationship("Job", back_populates="business")

    @property
    def is_active(self) -> bool:
        return not self.paused


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("business_id", "phone", name="uq_customer_phone"),)

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(160), nullable=True)
    phone = Column(String(24), nullable=False, index=True)
    email = Column(String(160), nullable=True)
    address_line1 = Column(String(240), nullable=True)
    city = Column(String(120), nullable=True)
    postal_code = Column(String(12), nullable=True)
    notes = Column(Text, nullable=True)

    # CASL bookkeeping
    sms_consent = Column(Boolean, default=False, nullable=False)
    sms_consent_source = Column(String(40), nullable=True)
    sms_consent_at = Column(UTCDateTime(), nullable=True)
    sms_opt_out_at = Column(UTCDateTime(), nullable=True)

    business = relationship("Business", back_populates="customers")
    jobs = relationship("Job", back_populates="customer")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("business_id", "number", name="uq_job_number"),)

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    number = Column(Integer, nullable=False)  # short human ref used in owner SMS

    service_key = Column(String(60), nullable=False)
    service_name = Column(String(160), nullable=False)
    status = Column(String(24), default="requested", nullable=False, index=True)
    source = Column(String(16), default="voice", nullable=False)

    scheduled_start = Column(UTCDateTime(), nullable=True, index=True)
    scheduled_end = Column(UTCDateTime(), nullable=True)
    window_label = Column(String(80), nullable=True)
    requested_for = Column(String(160), nullable=True)

    address = Column(String(240), nullable=True)
    price_estimate_low_cents = Column(Integer, nullable=True)
    price_estimate_high_cents = Column(Integer, nullable=True)
    price_final_cents = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    reminder_sent_at = Column(UTCDateTime(), nullable=True)
    review_requested_at = Column(UTCDateTime(), nullable=True)
    rebook_due_at = Column(UTCDateTime(), nullable=True)
    rebook_sent_at = Column(UTCDateTime(), nullable=True)
    completed_at = Column(UTCDateTime(), nullable=True)

    business = relationship("Business", back_populates="jobs")
    customer = relationship("Customer", back_populates="jobs")
    invoices = relationship("Invoice", back_populates="job")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )

    number = Column(String(32), nullable=False)
    status = Column(String(16), default="draft", nullable=False, index=True)
    method = Column(String(16), default="stripe")  # stripe | etransfer | cash

    subtotal_cents = Column(Integer, nullable=False, default=0)
    tax_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False, default=0)
    tax_breakdown = Column(JSON, default=list)  # [{label, rate, amount_cents}]
    line_items = Column(JSON, default=list)
    notes = Column(Text, nullable=True)

    payment_url = Column(String(600), nullable=True)
    stripe_session_id = Column(String(160), nullable=True)
    etransfer_email = Column(String(160), nullable=True)

    issued_at = Column(UTCDateTime(), nullable=True)
    due_at = Column(UTCDateTime(), nullable=True)
    paid_at = Column(UTCDateTime(), nullable=True)
    paid_via = Column(String(24), nullable=True)
    reminders_sent = Column(Integer, default=0, nullable=False)
    last_reminded_at = Column(UTCDateTime(), nullable=True)

    business = relationship("Business")
    job = relationship("Job", back_populates="invoices")
    customer = relationship("Customer")


class Message(Base, TimestampMixin):
    """Every outbound/inbound SMS. The audit trail for CASL and support."""

    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    invoice_id = Column(String(36), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)

    direction = Column(String(8), nullable=False)  # in | out
    to_number = Column(String(24), nullable=True)
    from_number = Column(String(24), nullable=True)
    body = Column(Text, nullable=False)
    template = Column(String(60), nullable=True)
    provider = Column(String(16), default="twilio")
    provider_sid = Column(String(80), nullable=True, index=True)
    status = Column(String(24), default="queued")
    meta = Column(JSON, default=dict)


class Call(Base, TimestampMixin):
    """Voice-agent record: transcript, summary, and the tools it invoked."""

    __tablename__ = "calls"

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id = Column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)

    provider = Column(String(16), default="vapi")
    provider_call_id = Column(String(120), nullable=True, index=True)
    direction = Column(String(8), default="in")
    caller_number = Column(String(24), nullable=True)
    called_number = Column(String(24), nullable=True)
    status = Column(String(24), default="in_progress")
    duration_seconds = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    tool_calls = Column(JSON, default=list)
    recording_url = Column(String(600), nullable=True)
    started_at = Column(UTCDateTime(), nullable=True)
    ended_at = Column(UTCDateTime(), nullable=True)


class WebhookEvent(Base):
    """Idempotency ledger — providers retry aggressively."""

    __tablename__ = "webhook_events"

    id = Column(String(36), primary_key=True, default=new_id)
    provider = Column(String(24), nullable=False)
    external_id = Column(String(200), nullable=False)
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_webhook_event"),)


class OnboardingDraft(Base):
    """Text-message onboarding in progress (no business exists yet)."""

    __tablename__ = "onboarding_drafts"

    id = Column(String(36), primary_key=True, default=new_id)
    phone = Column(String(24), nullable=False, index=True)
    step = Column(String(40), nullable=False, default="trade")
    data = Column(JSON, default=dict)
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class LoginCode(Base):
    """One-time owner login code (hashed)."""

    __tablename__ = "login_codes"

    id = Column(String(36), primary_key=True, default=new_id)
    business_id = Column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone = Column(String(24), nullable=False)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(UTCDateTime(), nullable=False)
    used_at = Column(UTCDateTime(), nullable=True)
    created_at = Column(UTCDateTime(), default=utcnow, nullable=False)
