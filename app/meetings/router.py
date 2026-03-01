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

    Participants who haven't connected Google Calendar are handled gracefully:
      - Registered + connected   → fetch busy blocks from Google Calendar API
      - Registered + no OAuth    → fetch busy blocks from internal DB meetings
      - Not registered at all    → treated as always free, warning added
    """
    # Always include the current user as a participant
    all_participants = list(set(payload.participants + [current_user.email]))

    # ── Build busy_map manually so we can apply the same DB fallback
    # as /availability — service.py only checks Google, not internal DB ──────
    import pytz
    busy_map = {}
    warnings = []

    search_start = payload.start_date
    search_end   = payload.end_date

    # Naive UTC boundaries for DB queries (DB stores local-input times)
    db_start = search_start.replace(tzinfo=None) if search_start.tzinfo else search_start
    db_end   = search_end.replace(tzinfo=None)   if search_end.tzinfo   else search_end

    for email in all_participants:
        user = db.query(User).filter(User.email == email).first()

        if user and user.access_token:
            # ── Connected to Google → fetch from Calendar API ─────────────
            try:
                service, _ = get_calendar_service(
                    access_token  = user.access_token,
                    refresh_token = user.refresh_token,
                    token_expiry  = user.token_expiry,
                )
                busy_map[email] = fetch_busy_blocks(service, search_start, search_end)
            except Exception as exc:
                warnings.append(f"Could not fetch calendar for {email}: {str(exc)}")
                busy_map[email] = []

        elif user and not user.access_token:
            # ── Registered but not connected → fall back to internal DB ───
            db_meetings = (
                db.query(Meeting)
                .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
                .filter(
                    MeetingParticipant.email == email,
                    Meeting.scheduled_start  >= db_start,
                    Meeting.scheduled_end    <= db_end,
                    Meeting.status           == "confirmed",
                )
                .all()
            )
            busy_map[email] = [
                {"start": m.scheduled_start, "end": m.scheduled_end}
                for m in db_meetings
            ]
            warnings.append(
                f"{email} has not connected Google Calendar. "
                "Showing availability from internal meetings only."
            )

        else:
            # ── Not registered at all → treat as always free ──────────────
            busy_map[email] = []
            warnings.append(
                f"{email} is not registered. Their availability could not be checked."
            )

    # ── Rank the candidate slots ──────────────────────────────────────────
    from app.meetings.ranking import generate_candidate_slots, rank_slots
    candidates   = generate_candidate_slots(search_start, search_end, payload.duration_minutes)
    ranked_slots = rank_slots(
        candidate_slots    = candidates,
        busy_map           = busy_map,
        total_participants = len(all_participants),
        search_start       = search_start,
        search_end         = search_end,
        is_priority        = payload.is_priority,
    )[:payload.max_slots]

    if not ranked_slots:
        warnings.append("No available slots found for the given participants and time window.")

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

    Two sources of busy data:
      1. Google Calendar API  — for registered users who have connected Google
      2. Internal DB meetings — for participants who haven't connected Google
                                (covers the case of vroomrentalsystem@gmail.com
                                 being added as participant but never logged in)
    """
    import pytz
    import datetime as _dt

    # ── Resolve the user's local timezone ────────────────────────────────────
    try:
        local_tz = pytz.timezone(payload.timezone)   # e.g. Asia/Karachi
    except pytz.UnknownTimeZoneError:
        local_tz = pytz.utc

    # ── Compute day boundaries in LOCAL time, then convert to UTC for Google ─
    # Example for Asia/Karachi (UTC+5):
    #   Local day start = 2026-03-02 00:00:00 PKT
    #   UTC equivalent  = 2026-03-01 19:00:00 UTC   ← what we send to Google
    local_midnight = payload.date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    local_end      = payload.date.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=None)

    local_day_start = local_tz.localize(local_midnight)
    local_day_end   = local_tz.localize(local_end)

    utc_day_start = local_day_start.astimezone(pytz.utc)
    utc_day_end   = local_day_end.astimezone(pytz.utc)

    # DB stores the local time the user entered (not UTC).
    # So filter the DB using local day boundaries, not UTC boundaries.
    db_day_start = local_midnight   # e.g. 2026-03-02 00:00:00 (local, naive)
    db_day_end   = local_end        # e.g. 2026-03-02 23:59:59 (local, naive)

    all_emails = list(set(payload.participants + [current_user.email]))
    timelines  = []
    warnings   = []

    def _fmt_local(dt) -> str:
        """
        Convert a UTC-aware datetime from Google to local timezone string.
        This is the core fix: Google returns 07:00 UTC, we display 12:00 PKT.
        """
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        local_dt = dt.astimezone(local_tz)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")

    for email in all_emails:
        user        = db.query(User).filter(User.email == email).first()
        busy_blocks = []

        # ── Source 1: Google Calendar API (for connected users) ───────────
        if user and user.access_token:
            try:
                service, _ = get_calendar_service(
                    access_token  = user.access_token,
                    refresh_token = user.refresh_token,
                    token_expiry  = user.token_expiry,
                )
                # fetch_busy_blocks now returns UTC-aware datetimes
                google_busy = fetch_busy_blocks(service, utc_day_start, utc_day_end)
                busy_blocks.extend([
                    {
                        # Convert UTC → local timezone before returning to client
                        "start": _fmt_local(b["start"]),
                        "end":   _fmt_local(b["end"]),
                    }
                    for b in google_busy
                ])
            except Exception as e:
                warnings.append(f"Could not fetch Google Calendar for {email}: {str(e)}")

        else:
            # ── Source 2: Internal DB meetings (fallback) ─────────────────
            # Participants who haven't connected Google OAuth still show their
            # busy time from meetings stored in our own DB.
            db_meetings = (
                db.query(Meeting)
                .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
                .filter(
                    MeetingParticipant.email == email,
                    Meeting.scheduled_start  >= db_day_start,
                    Meeting.scheduled_end    <= db_day_end,
                    Meeting.status           == "confirmed",
                )
                .all()
            )
            busy_blocks.extend([
                {
                    # DB stores the local time the user originally entered (e.g. 12:00 PKT).
                    # Do NOT treat it as UTC and convert — that would add +5 again → 17:00.
                    # Just format it directly as-is since it is already in local time.
                    "start": m.scheduled_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end":   m.scheduled_end.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for m in db_meetings
            ])

            if not user:
                warnings.append(f"{email} is not registered. Showing no availability.")
            else:
                warnings.append(
                    f"{email} has not connected Google Calendar. "
                    f"Showing availability from internal meetings only.",
                )

        timelines.append(mschemas.ParticipantTimeline(email=email, busy_blocks=busy_blocks))

    return mschemas.AvailabilityResponse(
        date         = local_midnight.strftime("%Y-%m-%d"),
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