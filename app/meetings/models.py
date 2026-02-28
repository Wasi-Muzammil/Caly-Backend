import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database.base import Base

def gen_uuid():
    return str(uuid.uuid4())

class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True, default=gen_uuid) # Pass function name
    title = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    is_priority = Column(Boolean, default=False)
    status = Column(String, default="pending")
    
    # Links to the User who created the meeting
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship: Connects to the MeetingParticipant table
    participants = relationship("MeetingParticipant", back_populates="meeting", cascade="all, delete-orphan")


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    id = Column(String, primary_key=True, default=gen_uuid)
    meeting_id = Column(String, ForeignKey("meetings.id"), nullable=False)
    
    # Optional: If the participant is a registered user, link their ID
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    
    email = Column(String, nullable=False)
    status = Column(String, default="invited")

    # Relationship: Connects back to the Meeting table
    meeting = relationship("Meeting", back_populates="participants")