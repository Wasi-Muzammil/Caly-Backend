import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.database.base import Base

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    
    # Google OAuth fields
    google_id = Column(String, unique=True, nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # RELATIONSHIPS: This connects the User to their Meetings
    # 1. Meetings this user created
    created_meetings = relationship("Meeting", backref="creator")
    
    # 2. Meetings this user is attending (if you linked user_id in MeetingParticipant)
    participations = relationship("MeetingParticipant", backref="user")
