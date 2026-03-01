"""
Meetings Router
===============
Endpoints:
  POST /meeting/suggest          — rank available slots for a set of participants
  POST /meeting/create           — confirm/book a slot + send email confirmations
  POST /meeting/availability     — visual timeline of busy blocks per participant
  GET  /meeting/                 — list meetings for current user
  DELETE /meeting/{meeting_id}   — delete a meeting (creator only)
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.security import get_current_user
from app.users.models import User
from app.meetings import schemas as mschemas
from app.meetings.models import Meeting, MeetingParticipant
from app.meetings.service import get_availability_and_rank
from app.calendar.service import get_calendar_service, fetch_busy_blocks
from app.email.email_service import send_confirmation_emails
import datetime

router = APIRouter()


# ─────────────────────────────────────────────
# POST /meeting/suggest
# Step 1: Find and rank available slots
# ─────────────────────────────────────────────

@router.post("/suggest", response_model=mschemas.SuggestResponse)
def suggest_slots(
    payload: mschemas.SuggestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compare all participants' Google Calendar availability and return
    ranked meeting slot suggestions.
    """
    # Always include the current user as a participant
    all_participants = list(set(payload.participants + [current_user.email]))

    ranked_slots, warnings = get_availability_and_rank(
        db                = db,
        participant_emails = all_participants,
        duration_minutes   = payload.duration_minutes,
        search_start       = payload.start_date,
        search_end         = payload.end_date,
        is_priority        = payload.is_priority,
        max_slots          = payload.max_slots,
    )

    if not ranked_slots:
        warnings.append("No available slots found for all participants in the given window.")

    return mschemas.SuggestResponse(slots=ranked_slots, warnings=warnings)


# ─────────────────────────────────────────────
# POST /meeting/create
# Step 2: Confirm a slot, save to DB, push to Google Calendar, send emails
# ─────────────────────────────────────────────

@router.post("/create", response_model=mschemas.MeetingResponse)
def create_meeting(
    payload: mschemas.ConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Book the chosen slot:
      1. Save meeting + participants to DB
      2. Push event to creator's Google Calendar
      3. Send confirmation emails to all participants
    """
    end_time = payload.start + timedelta(minutes=payload.duration_minutes)

    # ── 1. Save to DB ─────────────────────────────────────────────────────
    new_meeting = Meeting(
        title            = payload.title,
        duration_minutes = payload.duration_minutes,
        scheduled_start  = payload.start,
        scheduled_end    = end_time,
        is_priority      = payload.is_priority,
        status           = "confirmed",
        created_by       = current_user.id,
    )
    db.add(new_meeting)
    db.flush()   # get new_meeting.id before adding participants

    all_emails = list(set(payload.participants + [current_user.email]))

    for email in all_emails:
        participant_user = db.query(User).filter(User.email == email).first()
        db.add(MeetingParticipant(
            meeting_id = new_meeting.id,
            email      = email,
            user_id    = participant_user.id if participant_user else None,
        ))

    db.commit()
    db.refresh(new_meeting)

    # ── 2. Push to Google Calendar (creator's calendar) ───────────────────
    if current_user.access_token:
        try:
            from app.calendar.service import create_event
            service, creds = get_calendar_service(
                access_token  = current_user.access_token,
                refresh_token = current_user.refresh_token,
                token_expiry  = current_user.token_expiry,
            )
            # isoformat() on a timezone-aware datetime includes the offset
            # e.g. 2024-01-15T12:00:00+05:00  ← Google Calendar reads this correctly
            create_event(service, {
                "summary":     payload.title,
                "start_time":  payload.start.isoformat(),   # preserves +05:00 offset
                "end_time":    end_time.isoformat(),         # preserves +05:00 offset
                "timezone":    payload.timezone,
                "description": payload.description or "",
                "location":    payload.location or "",
                "attendees":   all_emails,
            })
            # Persist refreshed token if needed
            if creds.token != current_user.access_token:
                current_user.access_token = creds.token
                if creds.expiry:
                    current_user.token_expiry = creds.expiry
                db.commit()
        except Exception as e:
            # Don't abort the whole meeting creation if calendar push fails
            pass

    # ── 3. Send confirmation emails ───────────────────────────────────────
    send_confirmation_emails(
        participants = all_emails,
        title        = payload.title,
        start        = payload.start,
        end          = end_time,
        organizer    = current_user.email,
        location     = payload.location or "",
        description  = payload.description or "",
        is_priority  = payload.is_priority,
    )

    return mschemas.MeetingResponse(
        id           = new_meeting.id,
        title        = new_meeting.title,
        start        = new_meeting.scheduled_start,
        end          = new_meeting.scheduled_end,
        is_priority  = new_meeting.is_priority,
        status       = new_meeting.status,
        created_by   = current_user.email,
        participants = all_emails,
    )


# ─────────────────────────────────────────────
# GET /meeting/availability
# Visual timeline — busy blocks per participant for a given day
# ─────────────────────────────────────────────

@router.post("/availability", response_model=mschemas.AvailabilityResponse)
def get_availability_timeline(
    payload: mschemas.AvailabilityRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return each participant's busy blocks for a given date.
    Used to render the visual calendar-style availability timeline.
    """
    # Scope the search to the full requested day (UTC)
    day_start = payload.date.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    day_end   = payload.date.replace(hour=23, minute=59, second=59, microsecond=0)

    all_emails   = list(set(payload.participants + [current_user.email]))
    timelines    = []
    warnings     = []

    for email in all_emails:
        user = db.query(User).filter(User.email == email).first()

        if not user or not user.access_token:
            warnings.append(f"{email} has not connected Google Calendar.")
            timelines.append(mschemas.ParticipantTimeline(email=email, busy_blocks=[]))
            continue

        try:
            service, _ = get_calendar_service(
                access_token  = user.access_token,
                refresh_token = user.refresh_token,
                token_expiry  = user.token_expiry,
            )
            busy = fetch_busy_blocks(service, day_start, day_end)
            timelines.append(mschemas.ParticipantTimeline(
                email       = email,
                busy_blocks = [{"start": str(b["start"]), "end": str(b["end"])} for b in busy],
            ))
        except Exception as e:
            warnings.append(f"Could not fetch calendar for {email}: {str(e)}")
            timelines.append(mschemas.ParticipantTimeline(email=email, busy_blocks=[]))

    return mschemas.AvailabilityResponse(
        date         = payload.date.strftime("%Y-%m-%d"),
        participants = timelines,
        warnings     = warnings,
    )


# ─────────────────────────────────────────────
# GET /meeting/
# List meetings for current user
# ─────────────────────────────────────────────

@router.get("/", response_model=list[mschemas.MeetingResponse])
def list_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all meetings the current user is participating in."""
    meetings = (
        db.query(Meeting)
        .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
        .filter(MeetingParticipant.email == current_user.email)
        .all()
    )

    return [
        mschemas.MeetingResponse(
            id           = m.id,
            title        = m.title,
            start        = m.scheduled_start,
            end          = m.scheduled_end,
            is_priority  = m.is_priority,
            status       = m.status,
            created_by   = current_user.email,
            participants = [p.email for p in m.participants],
        )
        for m in meetings
    ]


# ─────────────────────────────────────────────
# DELETE /meeting/{meeting_id}
# ─────────────────────────────────────────────

@router.delete("/{meeting_id}")
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a meeting. Only the creator is allowed to do this."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this meeting")

    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted successfully"}