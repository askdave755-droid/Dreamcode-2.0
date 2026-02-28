from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import secrets
import string

Base = declarative_base()

def generate_referral_code():
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"DREAM-{code[:4]}-{code[4:]}"

class Dream(Base):
    __tablename__ = "dreams"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, index=True)
    dream_text = Column(Text)
    emotion = Column(String)
    colors = Column(String)
    symbols = Column(String)
    interpretation = Column(Text, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    referral_code = Column(String, unique=True, index=True, default=generate_referral_code)
    referred_by = Column(String, ForeignKey("dreams.id"), nullable=True)
    
    # This is the key fix - simple relationship without back_populates
    referrals = relationship("Dream", foreign_keys="Dream.referred_by")
