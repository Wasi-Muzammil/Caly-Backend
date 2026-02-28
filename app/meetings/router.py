from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.meetings import schemas as mschemas
from app.meetings.models import Meeting, MeetingParticipant

router = APIRouter()

@router.post("/create")
def create_meeting(request: Request, payload: mschemas.ConfirmRequest, db: Session = Depends(get_db)):
    # 1. Get the current user's email from the session
    user_info = request.session.get("user")
    if not user_info:
        raise HTTPException(status_code=401, detail="Please login first")
    
    current_user_email = user_info.get("email")

    # 2. Calculate end time
    end_time = payload.start + timedelta(minutes=payload.duration_minutes)

    # 3. Create the Meeting object
    new_meeting = Meeting(
        title=payload.title,
        duration_minutes=payload.duration_minutes,
        scheduled_start=payload.start,
        scheduled_end=end_time,
        is_priority=payload.is_priority,
        status="confirmed",
        created_by=current_user_email 
    )
    
    db.add(new_meeting)
    db.commit()
    db.refresh(new_meeting)

    # 4. Add the participants (including the creator)
    all_emails = set(payload.participants)
    all_emails.add(current_user_email)

    for email in all_emails:
        participant = MeetingParticipant(meeting_id=new_meeting.id, email=email)
        db.add(participant)
    
    db.commit()

    return {"id": new_meeting.id, "title": new_meeting.title, "created_by": current_user_email}


@router.get("/")
def list_meetings(db: Session = Depends(get_db)):
    # Fetch all meetings and their participants using a simple query
    meetings = db.query(Meeting).all()
    
    results = []
    for m in meetings:
        results.append({
            "id": m.id,
            "title": m.title,
            "start": m.scheduled_start,
            "end": m.scheduled_end,
            "participants": [p.email for p in m.participants]
        })
    return results