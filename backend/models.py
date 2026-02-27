from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

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
    referral_code = Column(String, unique=True, index=True)
    referred_by = Column(String, ForeignKey("dreams.id"), nullable=True)
