from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import secrets
import string

def generate_referral_code():
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"DREAM-{code[:4]}-{code[4:]}"

class Dream(Base):
    __tablename__ = "dreams"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    dream_text = Column(Text, nullable=False)
    emotion = Column(String)
    colors = Column(String)
    symbols = Column(String)
    teaser = Column(Text)
    full_report = Column(JSON)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    
    # Referral system
    referral_code = Column(String, unique=True, index=True, default=generate_referral_code)
    referred_by = Column(String, ForeignKey("dreams.id"), nullable=True)
    referral_count = Column(Integer, default=0)
    discount_applied = Column(Boolean, default=False)
    
    referrals = relationship("Dream", backref="parent", remote_side=[id], lazy="dynamic")
