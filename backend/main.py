from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import openai
import stripe
import os
import json
import uuid
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from database import get_db, engine
from models import Base, Dream
from pdf_generator import generate_dream_pdf, get_hebrew_year
from email_service import send_dream_email, send_referrer_notification, send_test_email, email_provider

load_dotenv()

# Initialize database tables (non-fatal if DB is temporarily unreachable —
# the app must still boot so /health can report what's wrong)
try:
    if engine is not None:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables verified")
    else:
        print("⚠️ DATABASE_URL not set — skipping table creation")
except Exception as e:
    print(f"⚠️ Database init failed (app will still serve /health): {e}")

def _run_startup_migrations():
    """Relax dreams.name / dreams.email to nullable on existing databases.

    create_all() only creates missing tables — it never alters columns — so
    databases created before the trust rework still have NOT NULL constraints.
    This ALTER is idempotent and safe to run on every boot. Postgres only;
    wrapped so a failure can never crash startup.
    """
    if engine is None:
        return
    try:
        if engine.dialect.name != "postgresql":
            return
    except Exception:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE dreams ALTER COLUMN name DROP NOT NULL"))
            conn.execute(text("ALTER TABLE dreams ALTER COLUMN email DROP NOT NULL"))
        print("✅ Startup migration: dreams.name/email are now nullable")
    except Exception as e:
        print(f"⚠️ Startup migration skipped/failed (non-fatal): {e}")

_run_startup_migrations()

app = FastAPI(title="DreamDecode API")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class DreamInput(BaseModel):
    # Name and email are NOT required up front: visitors get a free preview
    # with just their dream. Email is collected later, only to subscribe.
    name: Optional[str] = None
    email: Optional[str] = None
    dream_text: str
    emotion: Optional[str] = None
    colors: Optional[str] = None
    symbols: Optional[str] = None
    referral_code: Optional[str] = None

class CheckoutRequest(BaseModel):
    dream_id: str
    # Email is supplied at subscribe time (used for the Stripe customer,
    # the receipt, and report delivery) and saved onto the dream record.
    email: Optional[str] = None

class PaymentVerify(BaseModel):
    session_id: str
    dream_id: str

class FreeReportRequest(BaseModel):
    dream_id: str

class PortalRequest(BaseModel):
    email: str

# OpenAI client — lazy init so a missing key never crashes startup
_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set")
        _openai_client = openai.OpenAI(api_key=api_key)
    return _openai_client

def _clean_frontend_url():
    """Read + validate FRONTEND_URL, raising a clear error if misconfigured"""
    raw_frontend_url = os.getenv("FRONTEND_URL", "")
    if not raw_frontend_url:
        raise HTTPException(status_code=500, detail="FRONTEND_URL not configured")
    frontend_url = raw_frontend_url.strip().strip('"').strip("'").rstrip('/')
    if not frontend_url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=500, detail=f"Invalid FRONTEND_URL format: {frontend_url}")
    return frontend_url

def _trial_days() -> int:
    """Free-trial length from env (0 = no trial). Bad values fail safe to 0."""
    try:
        return max(0, int(os.getenv("TRIAL_DAYS", "0") or "0"))
    except ValueError:
        return 0

def _customer_has_active_subscription(email: str) -> bool:
    """True ONLY if this email has an active/trialing subscription to the
    DreamDecode price itself (STRIPE_PRICE_ID). Other products in the same
    Stripe account (e.g. DisputeTrack) must NOT unlock DreamDecode reports."""
    price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
    if not price_id:
        return False
    customers = stripe.Customer.list(email=email, limit=10)
    for customer in customers.data:
        for status in ("active", "trialing"):
            subs = stripe.Subscription.list(customer=customer.id, status=status, limit=20)
            for sub in subs.data:
                for item in sub["items"]["data"]:
                    if item["price"]["id"] == price_id:
                        return True
    return False

def generate_teaser(dream_data: dict):
    """Generate a 2-sentence free-preview teaser using GPT-4o-mini.

    The teaser hints at possible themes worth reflecting on — it must never
    declare what the dream means or claim divine authority.
    """
    prompt = f"""You are helping a Christian reflect on a dream through a biblical lens. 
    Write a compelling 2-sentence preview that:
    1. References ONE specific detail from the dream (color, object, or feeling)
    2. Suggests it may hold themes worth prayerful reflection, without declaring any meaning
    3. Uses warm, biblical language
    4. Ends with gentle intrigue (ellipsis or "but...")
    
    Dream: {dream_data['dream_text']}
    Feeling: {dream_data.get('emotion') or 'not specified'}
    Colors: {dream_data.get('colors') or 'none mentioned'}
    
    Write only the 2-sentence preview, nothing else."""
    
    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI teaser error: {e}")
        return "Something in your dream stands out as worth prayerful reflection... but its fuller themes are still waiting to be explored."

def generate_full_report(dream_data: dict):
    """Generate full biblical interpretation using GPT-4o.

    Methodology inspired by the hermeneutic framework of
    "The Divinity Code to Understanding Your Dreams and Visions"
    (Thompson & Beale): dreams are parables — metaphorical language
    from God that must be decoded symbol-by-symbol through Scripture,
    with discernment of the dream's source. All meanings are generated
    from the Bible itself (no proprietary dictionary content is copied).
    """
    system_prompt = """You are a thoughtful, humble guide helping Christians reflect on their dreams through a biblical lens, in the spirit of Joseph (Genesis 40-41) and Daniel (Daniel 2, 4, 7).

WHO YOU ARE — AND ARE NOT:
- You suggest POSSIBLE themes, questions, and Scripture passages for personal reflection.
- You do NOT prophesy, do NOT claim divine authority, and NEVER declare God's definitive meaning for someone's dream.
- You do NOT replace Scripture, prayer, or pastoral counsel — say so, and encourage the dreamer to bring significant dreams to a trusted pastor or mature believer.

CORE REFLECTIVE FRAMEWORK:
1. DREAMS CAN BE LIKE PARABLES. Jesus taught in parables (Psalm 78:2, Mark 4:34), and Scripture records God speaking through dreams. Explore the dream's imagery as possible metaphorical and spiritual themes — always as possibilities, never verdicts.
2. EVERY SYMBOL IS WORTH CONSIDERING. Reflect on each significant symbol (objects, people, animals, places, actions, body parts) individually, then weave the possibilities into a coherent set of themes to weigh.
3. NAMES AND PLACES MAY CARRY MEANING. In Scripture, names can reveal destiny (Abram→Abraham, Jacob→Israel). If a person or place appears, consider what that name or place may represent biblically — as one possibility among others.
4. COLORS CAN SUGGEST THEMES. Offer possible biblical associations for colors (e.g., white may suggest purity, red may suggest sacrifice or conflict, blue may suggest heaven, gold may suggest glory) — always as suggestions, never fixed codes.
5. NUMBERS MAY BE SIGNIFICANT. Offer possible biblical associations for numbers (e.g., 3, 7, 12, 40) as food for thought, not as certainties.
6. OFFER DISCERNMENT, NOT DECLARATIONS. Christians have traditionally weighed whether a dream seems consistent with:
   - GOD: edifying, aligned with Scripture, producing peace even when corrective, calling the dreamer higher
   - THE SOUL: the mind processing daily anxieties, memories, and emotions (Ecclesiastes 5:3)
   - A COUNTERFEIT (to be tested): fear-driven, condemning, hopelessly dark, or contradicting Scripture — to be tested against God's Word, not obeyed
   Offer which of these the dream's marks seem most consistent with — phrased as a prayerful consideration ("this dream has marks consistent with..."), never a declaration — and direct the dreamer to test it through Scripture, prayer, and wise counsel.
7. SCRIPTURE IS THE FINAL AUTHORITY. God never contradicts His written Word. Anchor every theme and symbol reflection to a specific verse, and encourage the dreamer to read each passage in context.
8. HUMILITY IN EVERY CLAIM. Use "may suggest," "could reflect," "is worth considering." Present multiple possibilities where they exist. Where a symbol has more than one biblical association (a lion pictures Christ in Revelation 5:5 and danger in 1 Peter 5:8), say so. Never assign one fixed meaning to any symbol.
9. TONE: Warm, humble, and honoring to the dreamer; hopeful even when raising hard questions. Never use fear, doom, flattery, or absolute pronouncements ("this dream means...," "God is telling you...").

Return STRICT JSON format:
{
    "discernment_note": "2-3 sentences reminding the dreamer these are possible themes to weigh prayerfully — not prophecy or a definitive message from God — and to test everything against Scripture, prayer, and pastoral counsel (1 Thessalonians 5:21).",
    "source_discernment": {
        "source": "God | Soul | Counterfeit (to be tested)",
        "explanation": "Which source this dream's marks seem most consistent with and why — reference the dream's fruit, tone, and alignment with Scripture. Phrase as a consideration, not a verdict.",
        "counsel": "How the dreamer might prayerfully steward this dream (e.g., journal and pray over it, release anxiety to God, test unsettling impressions against Scripture with a trusted counselor or pastor)"
    },
    "interpretations": [
        {"title": "A Theme to Reflect On", "meaning": "..."},
        {"title": "A Question to Weigh", "meaning": "..."},
        {"title": "A Possible Next Step", "meaning": "..."}
    ],
    "symbol_dictionary": [
        {
            "symbol": "The symbol exactly as it appeared in the dream",
            "biblical_meaning": "Possible metaphorical/spiritual associations drawn from Scripture — be specific, not generic; mention more than one association where Scripture supports it",
            "scripture": "Book Chapter:Verse supporting this reflection"
        }
    ],
    "scripture": {
        "reference": "Book Chapter:Verse",
        "text": "Full verse text",
        "context": "Why this applies"
    },
    "joseph_daniel_anchor": {
        "joseph": {
            "reference": "A specific verse from Joseph's dream interpretations (Genesis 40 or 41)",
            "connection": "How the symbolism or message of THIS dream parallels the dream Joseph interpreted (e.g., Pharaoh's cows, the cupbearer's vine, the baker's baskets) — be specific about the shared symbol or theme",
            "insight": "The interpretive principle from Joseph that applies to the dreamer now (e.g., seasons of preparation, favor after waiting, warning of coming change)"
        },
        "daniel": {
            "reference": "A specific verse from Daniel's dream/vision interpretations (Daniel 2, 4, or 7)",
            "connection": "How THIS dream parallels the vision Daniel interpreted (e.g., Nebuchadnezzar's statue, the great tree, the four beasts) — be specific about the shared symbol or theme",
            "insight": "The interpretive principle from Daniel that applies to the dreamer now (e.g., humility before promotion, God's sovereignty over seasons, the Most High rules in the affairs of men)"
        }
    },
    "prayer": "Personalized prayer using dream elements"
}

IMPORTANT: Include every significant symbol, color, number, name, and place from the dream in symbol_dictionary (typically 3-8 entries). If the dreamer listed symbols or colors explicitly, those MUST appear. Frame every entry as a possibility ("may suggest"), never a fixed code."""
    
    dreamer = dream_data.get('name') or "this dreamer"
    user_prompt = f"""Help {dreamer} reflect on this dream through a biblical lens:
    
    Content: {dream_data['dream_text']}
    Feeling that stood out: {dream_data.get('emotion') or 'Not specified'}
    Colors: {dream_data.get('colors') or 'Not specified'}
    Symbols: {dream_data.get('symbols') or 'Not specified'}
    
    Provide the JSON response."""
    
    try:
        response = get_openai_client().chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=3500,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI report error: {e}")
        dreamer_name = dream_data.get('name') or "Your child"
        return {
            "discernment_note": "These are possible themes to weigh prayerfully — not prophecy, and not a definitive message from God about your dream. Test everything against Scripture, prayer, and the counsel of a trusted pastor or mature believer (1 Thessalonians 5:21).",
            "source_discernment": {
                "source": "Worth discerning in prayer",
                "explanation": "Dreams that stir the heart toward God are worth stewarding prayerfully, for He has spoken in the night seasons (Job 33:14-16). Consider what fruit this dream bears as you pray over it.",
                "counsel": "Write this dream down, read the passages below in context, and discuss what stands out with a trusted counselor or pastor."
            },
            "interpretations": [
                {"title": "A Theme to Reflect On", "meaning": "Your dream may hold themes worth prayerful consideration — notice which images linger with you most."},
                {"title": "A Question to Weigh", "meaning": "What feelings and symbols stood out most vividly? Those are often the best starting points for journaling and prayer."},
                {"title": "A Possible Next Step", "meaning": "Pray for discernment, read the Scripture below in context, and consider discussing the dream with a trusted pastor or mature believer."}
            ],
            "symbol_dictionary": [
                {
                    "symbol": "The dream itself",
                    "biblical_meaning": "Scripture pictures God as one who can seal instruction in the heart during the night seasons, when the noise of the day is stilled — a possibility worth weighing, not a verdict.",
                    "scripture": "Job 33:14-16"
                },
                {
                    "symbol": "Vivid feelings",
                    "biblical_meaning": "The emotional weight of a dream may point to the area of life most worth bringing before God in prayer.",
                    "scripture": "Psalm 16:7"
                }
            ],
            "scripture": {
                "reference": "Proverbs 3:5-6",
                "text": "Trust in the LORD with all your heart and lean not on your own understanding.",
                "context": "Whatever a dream may suggest, trust and discernment belong with God and His Word."
            },
            "joseph_daniel_anchor": {
                "joseph": {
                    "reference": "Genesis 41:16",
                    "connection": "Joseph insisted that interpretations belong to God — a reminder to hold every reflection with humility.",
                    "insight": "Joseph waited years for his own dreams to unfold — faithfulness in the waiting matters as much as understanding."
                },
                "daniel": {
                    "reference": "Daniel 2:22",
                    "connection": "Daniel sought God in prayer before any interpretation came — the pursuit of God precedes clarity.",
                    "insight": "Bring your dream to God first in prayer, and let Scripture and wise counsel confirm what is worth holding onto."
                }
            },
            "prayer": f"Lord, guide {dreamer_name} as they reflect on this dream. Grant wisdom, peace, and discernment through Your Word and Your Spirit."
        }

@app.post("/api/analyze-teaser")
async def analyze_teaser(dream: DreamInput, db: Session = Depends(get_db)):
    """Generate teaser and save dream to database"""
    dream_id = str(uuid.uuid4())
    
    # Check for referrer
    referrer = None
    if dream.referral_code:
        referrer = db.query(Dream).filter(Dream.referral_code == dream.referral_code).first()
        print(f"Referrer found: {(referrer.name if referrer and referrer.name else 'None')}")
    
    # Generate teaser
    teaser_text = generate_teaser(dream.dict())
    
    # Create database record
    db_dream = Dream(
        id=dream_id,
        name=dream.name,
        email=dream.email,
        dream_text=dream.dream_text,
        emotion=dream.emotion,
        colors=dream.colors,
        symbols=dream.symbols,
        referred_by=referrer.id if referrer else None,
        is_paid=False
    )
    db.add(db_dream)
    db.commit()
    
    print(f"✅ Dream created: {dream_id} for {dream.email or 'anonymous preview'}")
    
    return {
        "dream_id": dream_id,
        "referral_code": db_dream.referral_code,
        "teaser": teaser_text,
        "hebrew_year": get_hebrew_year(),
        "discount_applied": True if referrer else False,
        "price": 4.99,
        "subscription": True,  # $4.99/mo unlocks unlimited full reports
        "trial_days": _trial_days()  # >0 means checkout offers a free trial first
    }

@app.get("/api/referral/{code}")
async def get_referral_info(code: str, db: Session = Depends(get_db)):
    """Get referral information for blessing display"""
    referrer = db.query(Dream).filter(Dream.referral_code == code).first()
    
    if not referrer:
        raise HTTPException(status_code=404, detail="Blessing code not found")
    
    referrer_display = referrer.name or "A friend"
    return {
        "referrer_name": referrer.name,  # may be null — frontend falls back to "A friend"
        "referrer_dream_preview": f"A blessed vision from {referrer_display}",
        "discount_active": False,
        "discount_percent": 0,
        "message": f"{referrer_display} has shared the gift of biblical dream reflection with you. Like the loaves and fishes, this blessing multiplies when shared."
    }

@app.post("/api/get-full-report")
async def get_full_report(request: FreeReportRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generate and return the full report — requires an active subscription.

    A dream becomes is_paid when the dreamer subscribes via checkout
    (verified in /api/verify-payment) or when /api/create-checkout-session
    finds an existing active DreamDecode subscription for their email.
    """
    dream = db.query(Dream).filter(Dream.id == request.dream_id).first()
    
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    
    if not dream.is_paid:
        raise HTTPException(status_code=402, detail="An active DreamDecode subscription ($4.99/mo) is required to unlock the full reflection report.")
    
    # Already generated — return cached version
    if dream.interpretation:
        return {
            "status": "revealed",
            "report": json.loads(dream.interpretation),
            "message": "Report already generated"
        }
    
    # Generate full report
    print(f"🤖 Generating report for: {dream.name or dream.email or dream.id}")
    report = generate_full_report({
        "name": dream.name,
        "dream_text": dream.dream_text,
        "emotion": dream.emotion,
        "colors": dream.colors,
        "symbols": dream.symbols
    })
    
    # Generate PDF
    pdf_bytes = generate_dream_pdf(dream.name, report)
    
    # Mark as unlocked (also enables PDF download endpoint)
    dream.is_paid = True
    dream.interpretation = json.dumps(report)
    db.commit()
    
    # Send email asynchronously
    background_tasks.add_task(
        send_dream_email,
        dream.email,
        dream.name,
        report,
        pdf_bytes,
        dream.referral_code
    )
    
    # Notify referrer if applicable
    if dream.referred_by:
        referrer = db.query(Dream).filter(Dream.id == dream.referred_by).first()
        if referrer and referrer.email:
            background_tasks.add_task(
                send_referrer_notification,
                referrer.email,
                referrer.name,
                dream.name
            )
    
    return {
        "status": "revealed",
        "report": report,
        "message": "Your full reflection report has been emailed to you"
    }

# ---- Billing: $4.99/month subscription ----

@app.post("/api/create-checkout-session")
async def create_checkout(request: CheckoutRequest, db: Session = Depends(get_db)):
    """Create a $4.99/mo subscription checkout — or unlock instantly if the
    dreamer's email already has an active DreamDecode subscription (never double-charge).
    Trial and intro-discount are configured via TRIAL_DAYS / TRIAL_COUPON_ID env vars."""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
    dream_id = request.dream_id
    
    print(f"🔍 Checkout requested for dream_id: {dream_id}")
    
    if not dream_id:
        raise HTTPException(status_code=400, detail="dream_id is required")
    
    dream = db.query(Dream).filter(Dream.id == dream_id).first()
    
    if not dream:
        print(f"❌ Dream not found: {dream_id}")
        raise HTTPException(status_code=404, detail="Dream not found")
    
    # Email is collected at subscribe time (not up front). It is required here:
    # Stripe needs it for the customer + receipt, and report delivery needs it.
    email = ((request.email or "") or (dream.email or "")).strip()
    if not email:
        raise HTTPException(
            status_code=400,
            detail="An email address is required to subscribe — it's used for your receipt and to deliver your report."
        )
    if email != dream.email:
        dream.email = email
        db.commit()

    frontend_url = _clean_frontend_url()
    
    # Already subscribed to DREAMDECODE under this email? Unlock without charging again.
    try:
        if _customer_has_active_subscription(email):
            dream.is_paid = True
            db.commit()
            print(f"✅ Existing subscriber — unlocked {dream_id} for {email} with no new charge")
            return {"already_subscribed": True, "dream_id": dream_id}
    except Exception as e:
        print(f"⚠️ Subscription lookup failed (continuing to checkout): {e}")
    
    if not price_id:
        raise HTTPException(status_code=500, detail="STRIPE_PRICE_ID not configured — set the $4.99/mo price ID in Railway variables")
    
    success_url = f"{frontend_url}/?session_id={{CHECKOUT_SESSION_ID}}&dream_id={dream_id}"
    cancel_url = f"{frontend_url}/?cancelled=1"
    
    # Trial / intro-discount config — change these in Railway variables, no redeploy needed:
    #   TRIAL_DAYS=7         → card collected, $0 today, first bill after N days
    #   TRIAL_COUPON_ID=...  → Stripe coupon ID auto-applied (e.g. 80% off once ≈ $1 first month)
    trial_days = _trial_days()
    trial_coupon = os.getenv("TRIAL_COUPON_ID", "").strip()
    
    subscription_data = {"metadata": {"dream_id": dream_id}}
    if trial_days > 0:
        subscription_data["trial_period_days"] = trial_days
    
    session_params = {
        "payment_method_types": ['card'],
        "line_items": [{'price': price_id, 'quantity': 1}],
        "mode": 'subscription',
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_email": email,
        "metadata": {"dream_id": dream_id},
        "subscription_data": subscription_data,
    }
    if trial_coupon:
        # Stripe forbids discounts + allow_promotion_codes on the same session
        session_params["discounts"] = [{"coupon": trial_coupon}]
    else:
        session_params["allow_promotion_codes"] = True
    
    print(f"Success URL: {success_url} | trial_days={trial_days} trial_coupon={'set' if trial_coupon else 'none'}")
    
    try:
        session = stripe.checkout.Session.create(**session_params)
        
        print(f"✅ Stripe subscription session created: {session.id}")
        
        return {
            "url": session.url,
            "session_id": session.id,
            "amount": 4.99,
            "interval": "month",
            "trial_days": trial_days
        }
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe API error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail=f"Payment setup failed: {e}")

@app.post("/api/verify-payment")
async def verify_payment(data: PaymentVerify, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Verify checkout (subscription or legacy one-time) and generate full report"""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    try:
        session = stripe.checkout.Session.retrieve(data.session_id)
        
        # Subscription checkouts confirm via the subscription's status;
        # legacy one-time payments confirm via payment_status.
        paid = False
        if session.mode == "subscription":
            if session.subscription:
                subscription = stripe.Subscription.retrieve(session.subscription)
                paid = subscription.status in ("active", "trialing")
                print(f"Subscription {subscription.id} status: {subscription.status}")
        else:
            paid = session.payment_status == "paid"
        
        if not paid:
            return {"status": "unpaid"}
        
        dream = db.query(Dream).filter(Dream.id == data.dream_id).first()
        
        if not dream:
            raise HTTPException(status_code=404, detail="Dream not found")
        
        # Check if already processed
        if dream.is_paid and dream.interpretation:
            return {
                "status": "paid",
                "report": json.loads(dream.interpretation),
                "message": "Report already generated"
            }
        
        # Generate full report
        print(f"🤖 Generating report for: {dream.name or dream.email or dream.id}")
        report = generate_full_report({
            "name": dream.name,
            "dream_text": dream.dream_text,
            "emotion": dream.emotion,
            "colors": dream.colors,
            "symbols": dream.symbols
        })
        
        # Generate PDF
        pdf_bytes = generate_dream_pdf(dream.name, report)
        
        # Update database
        dream.is_paid = True
        dream.interpretation = json.dumps(report)
        db.commit()
        
        # Send email asynchronously
        background_tasks.add_task(
            send_dream_email,
            dream.email,
            dream.name,
            report,
            pdf_bytes,
            dream.referral_code
        )
        
        # Notify referrer if applicable
        if dream.referred_by:
            referrer = db.query(Dream).filter(Dream.id == dream.referred_by).first()
            if referrer and referrer.email:
                background_tasks.add_task(
                    send_referrer_notification,
                    referrer.email,
                    referrer.name,
                    dream.name
                )
        
        return {
            "status": "paid",
            "report": report,
            "message": "Your full reflection report has been emailed to you"
        }
        
    except Exception as e:
        print(f"❌ Verification error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/create-portal-session")
async def create_portal_session(request: PortalRequest):
    """Open Stripe's customer portal so a subscriber can manage/cancel their plan"""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    email = request.email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")
    
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            raise HTTPException(status_code=404, detail="No subscription found for that email")
        
        frontend_url = _clean_frontend_url()
        session = stripe.billing_portal.Session.create(
            customer=customers.data[0].id,
            return_url=frontend_url,
        )
        return {"url": session.url}
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        print(f"❌ Portal error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe error: {e}")

@app.get("/api/download-pdf/{dream_id}")
async def download_pdf(dream_id: str, db: Session = Depends(get_db)):
    """Download generated PDF report"""
    from fastapi.responses import Response
    
    dream = db.query(Dream).filter(Dream.id == dream_id).first()
    
    if not dream or not dream.is_paid:
        raise HTTPException(status_code=404, detail="Report not found")
    
    report = json.loads(dream.interpretation) if dream.interpretation else {}
    pdf_bytes = generate_dream_pdf(dream.name, report)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=dream-reflection-{dream_id}.pdf"}
    )

@app.get("/api/test-email")
def test_email():
    """Diagnostic: send a test email via the active provider (Brevo or
    SendGrid) to the app's own FROM_EMAIL and return exactly what the
    provider said. Safe from abuse — it can only ever mail the sender
    address itself."""
    result = send_test_email()
    result["email_provider"] = email_provider() or "none"
    return result

@app.get("/health")
def health():
    """Health check endpoint — reports DB + config status for diagnostics"""
    db_status = "not_configured"
    if engine is not None:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)[:200]}"
    return {
        "status": "ok",
        "database": db_status,
        "openai_key": "set" if os.getenv("OPENAI_API_KEY") else "MISSING",
        "stripe_key": "set" if os.getenv("STRIPE_SECRET_KEY") else "MISSING",
        "stripe_price": "set" if os.getenv("STRIPE_PRICE_ID") else "MISSING",
        "trial_days": _trial_days(),
        "sendgrid_key": "set" if os.getenv("SENDGRID_API_KEY") else "not_set",
        "brevo_key": "set" if os.getenv("BREVO_API_KEY") else "not_set",
        "email_provider": email_provider() or "none",
        "frontend_url": os.getenv("FRONTEND_URL", "MISSING"),
        "hebrew_year": get_hebrew_year(),
        "timestamp": datetime.utcnow().isoformat()
    }
