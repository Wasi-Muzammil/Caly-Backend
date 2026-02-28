from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.security import get_current_user
from app.users.models import User
from app.meetings import schemas as mschemas
from app.meetings.models import Meeting, MeetingParticipant

router = APIRouter()


@router.post("/create")
def create_meeting(
    payload: mschemas.ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),   # JWT auth replaces request.session
):
    # 1. Calculate end time
    end_time = payload.start + timedelta(minutes=payload.duration_minutes)

    # 2. Create the Meeting — created_by uses user.id (FK), not email
    new_meeting = Meeting(
        title=payload.title,
        duration_minutes=payload.duration_minutes,
        scheduled_start=payload.start,
        scheduled_end=end_time,
        is_priority=payload.is_priority,
        status="confirmed",
        created_by=current_user.id,   # Fix: was using email, but FK points to users.id
    )

    db.add(new_meeting)
    db.flush()   # flush to get new_meeting.id before adding participants

    # 3. Add participants (always include the creator)
    all_emails = set(payload.participants)
    all_emails.add(current_user.email)

    for email in all_emails:
        # Check if this participant email belongs to a registered user
        participant_user = db.query(User).filter(User.email == email).first()

        participant = MeetingParticipant(
            meeting_id=new_meeting.id,
            email=email,
            user_id=participant_user.id if participant_user else None,  # link user_id if registered
        )
        db.add(participant)

    db.commit()
    db.refresh(new_meeting)

    return {
        "id": new_meeting.id,
        "title": new_meeting.title,
        "start": new_meeting.scheduled_start,
        "end": new_meeting.scheduled_end,
        "created_by": current_user.email,
    }


@router.get("/")
def list_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),   # protect this route too
):
    # Only return meetings the current user is part of (as creator or participant)
    meetings = (
        db.query(Meeting)
        .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
        .filter(MeetingParticipant.email == current_user.email)
        .all()
    )

    results = []
    for m in meetings:
        results.append({
            "id": m.id,
            "title": m.title,
            "start": m.scheduled_start,
            "end": m.scheduled_end,
            "is_priority": m.is_priority,
            "status": m.status,
            "participants": [p.email for p in m.participants],
        })

    return results


@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Only the creator can delete the meeting
    if meeting.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this meeting")

    db.delete(meeting)
    db.commit()

    return {"message": "Meeting deleted successfully"}