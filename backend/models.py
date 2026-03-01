from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

def generate_referral_code():
    """Generate 8-character referral code"""
    return str(uuid.uuid4())[:8].upper()

class Dream(Base):
    __tablename__ = "dreams"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    dream_text = Column(Text, nullable=False)
    emotion = Column(String, nullable=True)
    colors = Column(String, nullable=True)
    symbols = Column(String, nullable=True)
    
    # Payment status
    is_paid = Column(Boolean, default=False)
    interpretation = Column(Text, nullable=True)  # JSON string
    
    # Referral system
    referral_code = Column(String, unique=True, index=True, default=generate_referral_code)
    referred_by = Column(String, ForeignKey("dreams.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Dream {self.id} - {self.name}>"
