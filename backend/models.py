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
    # Name and email are optional at preview time — an email is only required
    # later, at subscribe (for the receipt and report delivery).
    # NOTE: existing databases need `ALTER TABLE dreams ALTER COLUMN name DROP NOT NULL`
    # and the same for email — applied automatically by _run_startup_migrations()
    # in main.py on Postgres.
    name = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)
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
