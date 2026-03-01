from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
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
from email_service import send_dream_email, send_referrer_notification

load_dotenv()

# Initialize database tables
Base.metadata.create_all(bind=engine)

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
    name: str
    email: str
    dream_text: str
    emotion: Optional[str] = None
    colors: Optional[str] = None
    symbols: Optional[str] = None
    referral_code: Optional[str] = None

class CheckoutRequest(BaseModel):
    dream_id: str

class PaymentVerify(BaseModel):
    session_id: str
    dream_id: str

# Initialize OpenAI
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_teaser(dream_data: dict):
    """Generate 2-sentence teaser using GPT-3.5"""
    prompt = f"""You are a biblical dream interpreter in the tradition of Joseph. 
    Analyze this dream and write a compelling 2-sentence teaser that:
    1. References ONE specific detail from the dream (color, object, or emotion)
    2. Hints at spiritual significance without fully explaining
    3. Uses biblical/mystical language
    4. Ends with mystery (ellipsis or "but...")
    
    Dream: {dream_data['dream_text']}
    Emotion: {dream_data.get('emotion', 'unknown')}
    Colors: {dream_data.get('colors', 'none mentioned')}
    
    Write only the 2-sentence teaser, nothing else."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI teaser error: {e}")
        return "A mysterious vision approaches your spirit... but its full meaning awaits revelation."

def generate_full_report(dream_data: dict):
    """Generate full biblical interpretation using GPT-4"""
    system_prompt = """You are a prophetic dream interpreter in the tradition of Joseph (Genesis 40-41) and Daniel (Daniel 2, 4, 7).
    
    Interpret using biblical typology:
    - Water = Holy Spirit, cleansing, or chaos
    - Fire = Pentecost, purification, or judgment  
    - Serpents = Deception or healing (Numbers 21:9)
    - Heights = Authority or pride
    - Doors = New seasons or vulnerabilities
    
    Return STRICT JSON format:
    {
        "interpretations": [
            {"title": "The Revelation", "meaning": "..."},
            {"title": "The Warning/Confirmation", "meaning": "..."},
            {"title": "The Action Step", "meaning": "..."}
        ],
        "scripture": {
            "reference": "Book Chapter:Verse",
            "text": "Full verse text",
            "context": "Why this applies"
        },
        "prayer": "Personalized prayer using dream elements"
    }"""
    
    user_prompt = f"""Interpret this dream for {dream_data['name']}:
    
    Content: {dream_data['dream_text']}
    Emotion: {dream_data.get('emotion', 'Not specified')}
    Colors: {dream_data.get('colors', 'Not specified')}
    Symbols: {dream_data.get('symbols', 'Not specified')}
    
    Provide the JSON response."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"OpenAI report error: {e}")
        return {
            "interpretations": [
                {"title": "The Revelation", "meaning": "Your dream carries spiritual significance that requires prayerful consideration."},
                {"title": "The Warning/Confirmation", "meaning": "Pay attention to the emotions and symbols that stood out most vividly."},
                {"title": "The Action Step", "meaning": "Pray for discernment and seek wise counsel from spiritual mentors."}
            ],
            "scripture": {
                "reference": "Proverbs 3:5-6",
                "text": "Trust in the LORD with all your heart and lean not on your own understanding.",
                "context": "God speaks through dreams, but interpretation belongs to Him."
            },
            "prayer": f"Lord, reveal the meaning of this vision to {dream_data['name']} according to Your wisdom and timing."
        }

@app.post("/api/analyze-teaser")
async def analyze_teaser(dream: DreamInput, db: Session = Depends(get_db)):
    """Generate teaser and save dream to database"""
    dream_id = str(uuid.uuid4())
    
    # Check for referrer
    referrer = None
    if dream.referral_code:
        referrer = db.query(Dream).filter(Dream.referral_code == dream.referral_code).first()
        print(f"Referrer found: {referrer.name if referrer else 'None'}")
    
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
    
    print(f"✅ Dream created: {dream_id} for {dream.email}")
    
    return {
        "dream_id": dream_id,
        "referral_code": db_dream.referral_code,
        "teaser": teaser_text,
        "hebrew_year": get_hebrew_year(),
        "discount_applied": True if referrer else False,
        "price": 8.50 if referrer else 17.00
    }

@app.get("/api/referral/{code}")
async def get_referral_info(code: str, db: Session = Depends(get_db)):
    """Get referral information for discount display"""
    referrer = db.query(Dream).filter(Dream.referral_code == code).first()
    
    if not referrer:
        raise HTTPException(status_code=404, detail="Blessing code not found")
    
    return {
        "referrer_name": referrer.name,
        "referrer_dream_preview": f"A blessed vision from {referrer.name}",
        "discount_active": True,
        "discount_percent": 50,
        "message": f"Your friend {referrer.name} has blessed you with a 50% discount on your dream interpretation. Like the loaves and fishes, this blessing multiplies when shared."
    }

@app.post("/api/create-checkout-session")
async def create_checkout(request: CheckoutRequest, db: Session = Depends(get_db)):
    """Create Stripe checkout session with URL validation"""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    dream_id = request.dream_id
    
    print(f"🔍 Checkout requested for dream_id: {dream_id}")
    
    if not dream_id:
        raise HTTPException(status_code=400, detail="dream_id is required")
    
    dream = db.query(Dream).filter(Dream.id == dream_id).first()
    
    if not dream:
        print(f"❌ Dream not found: {dream_id}")
        raise HTTPException(status_code=404, detail="Dream not found")
    
    print(f"✅ Found dream: {dream.email}, referred_by: {dream.referred_by}")
    
    # Get and clean FRONTEND_URL
    raw_frontend_url = os.getenv("FRONTEND_URL", "")
    print(f"Raw FRONTEND_URL: '{raw_frontend_url}'")
    
    if not raw_frontend_url:
        raise HTTPException(status_code=500, detail="FRONTEND_URL not configured")
    
    # Clean the URL - remove quotes, whitespace, trailing slashes
    frontend_url = raw_frontend_url.strip().strip('"').strip("'").rstrip('/')
    print(f"Cleaned FRONTEND_URL: '{frontend_url}'")
    
    # Validate URL format
    if not frontend_url.startswith(('http://', 'https://')):
        print(f"❌ Invalid URL format: {frontend_url}")
        raise HTTPException(status_code=500, detail=f"Invalid FRONTEND_URL format: {frontend_url}")
    
    # Calculate price
    amount = 850 if dream.referred_by else 1700  # $8.50 or $17.00 in cents
    
    # Build URLs carefully
    success_path = f"/reveal?session_id={{CHECKOUT_SESSION_ID}}&dream_id={dream_id}"
    cancel_path = "/cancel"
    
    success_url = f"{frontend_url}{success_path}"
    cancel_url = f"{frontend_url}{cancel_path}"
    
    print(f"Success URL: {success_url}")
    print(f"Cancel URL: {cancel_url}")
    
    try:
        # Create Stripe session
        session_params = {
            "payment_method_types": ['card'],
            "line_items": [{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': amount,
                    'product_data': {
                        'name': 'Complete Dream Revelation',
                        'description': f'Biblical interpretation for {dream.name}',
                    },
                },
                'quantity': 1,
            }],
            "mode": 'payment',
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": dream.email,
        }
        
        print(f"Creating Stripe session with params: {json.dumps(session_params, indent=2)}")
        
        session = stripe.checkout.Session.create(**session_params)
        
        print(f"✅ Stripe session created: {session.id}")
        
        return {
            "url": session.url, 
            "amount": amount / 100,
            "session_id": session.id
        }
        
    except stripe.error.StripeError as e:
        print(f"❌ Stripe API error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        raise HTTPException(status_code=400, detail=f"Payment setup failed: {str(e)}")

@app.post("/api/verify-payment")
async def verify_payment(data: PaymentVerify, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Verify payment and generate full report"""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    try:
        session = stripe.checkout.Session.retrieve(data.session_id)
        
        if session.payment_status != "paid":
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
        print(f"🤖 Generating report for: {dream.name}")
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
            if referrer:
                background_tasks.add_task(
                    send_referrer_notification,
                    referrer.email,
                    referrer.name,
                    dream.name
                )
        
        return {
            "status": "paid",
            "report": report,
            "message": "Your revelation has been emailed to you"
        }
        
    except Exception as e:
        print(f"❌ Verification error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

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
        headers={"Content-Disposition": f"attachment; filename=dream-revelation-{dream_id}.pdf"}
    )

@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "ok", 
        "hebrew_year": get_hebrew_year(),
        "timestamp": datetime.utcnow().isoformat()
    }
