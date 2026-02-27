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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="DreamDecode API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DreamInput(BaseModel):
    name: str
    email: str
    dream_text: str
    emotion: Optional[str] = None
    colors: Optional[str] = None
    symbols: Optional[str] = None
    referral_code: Optional[str] = None

class PaymentVerify(BaseModel):
    session_id: str
    dream_id: str

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_teaser(dream_data: dict):
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
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=150
    )
    
    return response.choices[0].message.content.strip()

def generate_full_report(dream_data: dict):
    system_prompt = """You are a prophetic dream interpreter in the tradition of Joseph (Genesis 40-41) and Daniel (Daniel 2, 4, 7).
    
    Interpret using biblical typology only:
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

@app.post("/api/analyze-teaser")
async def analyze_teaser(dream: DreamInput, db: Session = Depends(get_db)):
    dream_id = str(uuid.uuid4())
    
    referrer = None
    if dream.referral_code:
        referrer = db.query(Dream).filter(Dream.referral_code == dream.referral_code).first()
    
    teaser_text = generate_teaser(dream.dict())
    
    db_dream = Dream(
        id=dream_id,
        name=dream.name,
        email=dream.email,
        dream_text=dream.dream_text,
        emotion=dream.emotion,
        colors=dream.colors,
        symbols=dream.symbols,
        teaser=teaser_text,
        referred_by=referrer.id if referrer else None,
        discount_applied=True if referrer else False,
        status="pending"
    )
    db.add(db_dream)
    db.commit()
    
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
    referrer = db.query(Dream).filter(Dream.referral_code == code).first()
    
    if not referrer:
        raise HTTPException(status_code=404, detail="Blessing code not found")
    
    return {
        "referrer_name": referrer.name,
        "referrer_dream_preview": referrer.teaser[:100] + "..." if referrer.teaser else "A blessed vision",
        "discount_active": True,
        "discount_percent": 50,
        "message": f"Your friend {referrer.name} has blessed you with a 50% discount on your dream interpretation. Like the loaves and fishes, this blessing multiplies when shared."
    }

@app.post("/api/create-checkout-session")
async def create_checkout(data: dict, db: Session = Depends(get_db)):
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    dream_id = data.get('dream_id')
    
    dream = db.query(Dream).filter(Dream.id == dream_id).first()
    if not dream:
        raise HTTPException(status_code=404, detail="Dream not found")
    
    amount = 850 if dream.discount_applied else 1700
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
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
            mode='payment',
            success_url=f"{os.getenv('FRONTEND_URL')}/reveal?session_id={{CHECKOUT_SESSION_ID}}&dream_id={dream_id}",
            cancel_url=f"{os.getenv('FRONTEND_URL')}/cancel",
            customer_email=dream.email,
        )
        
        return {"url": session.url, "amount": amount / 100}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/verify-payment")
async def verify_payment(data: PaymentVerify, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    
    try:
        session = stripe.checkout.Session.retrieve(data.session_id)
        
        if session.payment_status == "paid":
            dream = db.query(Dream).filter(Dream.id == data.dream_id).first()
            
            if not dream:
                raise HTTPException(status_code=404, detail="Dream not found")
            
            if dream.status == "paid" and dream.full_report:
                return {
                    "status": "paid",
                    "report": dream.full_report,
                    "message": "Report already generated"
                }
            
            report = generate_full_report({
                "name": dream.name,
                "dream_text": dream.dream_text,
                "emotion": dream.emotion,
                "colors": dream.colors,
                "symbols": dream.symbols
            })
            
            pdf_bytes = generate_dream_pdf(dream.name, report)
            
            dream.status = "paid"
            dream.paid_at = datetime.utcnow()
            dream.full_report = report
            db.commit()
            
            background_tasks.add_task(
                send_dream_email,
                dream.email,
                dream.name,
                report,
                pdf_bytes,
                dream.referral_code
            )
            
            if dream.referred_by:
                referrer = db.query(Dream).filter(Dream.id == dream.referred_by).first()
                if referrer:
                    referrer.referral_count += 1
                    db.commit()
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
        else:
            return {"status": "unpaid"}
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/download-pdf/{dream_id}")
async def download_pdf(dream_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import Response
    
    dream = db.query(Dream).filter(Dream.id == dream_id).first()
    
    if not dream or dream.status != "paid":
        raise HTTPException(status_code=404, detail="Report not found")
    
    pdf_bytes = generate_dream_pdf(dream.name, dream.full_report)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=dream-revelation-{dream_id}.pdf"}
    )

@app.get("/health")
def health():
    return {"status": "ok", "hebrew_year": get_hebrew_year()}
