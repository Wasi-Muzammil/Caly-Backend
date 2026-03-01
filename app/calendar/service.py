from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import datetime
import os


# ─────────────────────────────────────────────
# Auth / Service Builder
# ─────────────────────────────────────────────

def get_calendar_service(access_token: str, refresh_token: str, token_expiry=None):
    """Build and return an authenticated Google Calendar service."""
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        expiry=token_expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    service = build("calendar", "v3", credentials=creds)
    return service, creds


# ─────────────────────────────────────────────
# Fetch Events
# ─────────────────────────────────────────────

def fetch_events(service, max_results: int = 10):
    """Fetch the next N upcoming events from the user's primary calendar."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    event_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return event_result.get("items", [])


# ─────────────────────────────────────────────
# RFC 3339 helper
# ─────────────────────────────────────────────

def _to_rfc3339(dt: datetime.datetime) -> str:
    """
    Safely convert any datetime to RFC 3339 for Google APIs.

    THE BUG THIS FIXES:
    If dt is timezone-aware (e.g. 2026-03-02T00:00:00+05:00), calling
    .isoformat() + "Z" produces "2026-03-02T00:00:00+05:00Z" which is
    malformed and causes Google to return 400 Bad Request.

    Fix: always convert to UTC first, then format with Z suffix.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────
# Fetch Free/Busy blocks for one user
# ─────────────────────────────────────────────

def fetch_busy_blocks(service, time_min: datetime.datetime, time_max: datetime.datetime) -> list[dict]:
    """
    Query the FreeBusy API for the user's primary calendar.
    Returns a list of {start, end} dicts representing UTC-naive datetimes.
    """
    body = {
        "timeMin": _to_rfc3339(time_min),
        "timeMax": _to_rfc3339(time_max),
        "items":   [{"id": "primary"}],
    }
    result   = service.freebusy().query(body=body).execute()
    raw_busy = result.get("calendars", {}).get("primary", {}).get("busy", [])

    busy_blocks = []
    for block in raw_busy:
        # Keep tzinfo=UTC so callers can convert to any local timezone.
        # Do NOT strip tzinfo here — that was the bug causing 07:00 UTC
        # to be returned as-is instead of being converted to 12:00 PKT.
        busy_blocks.append({
            "start": datetime.datetime.fromisoformat(block["start"].replace("Z", "+00:00")),
            "end":   datetime.datetime.fromisoformat(block["end"].replace("Z", "+00:00")),
        })
    return busy_blocks


# ─────────────────────────────────────────────
# Create Event
# ─────────────────────────────────────────────

def create_event(service, event_data: dict):
    """
    Insert a new event into the user's primary calendar.
    Only sends optional fields when they have real values to avoid 400 Bad Request.
    """
    event = {
        "summary": event_data["summary"],
        "start": {
            "dateTime": event_data["start_time"],
            "timeZone": event_data["timezone"],
        },
        "end": {
            "dateTime": event_data["end_time"],
            "timeZone": event_data["timezone"],
        },
    }
    if event_data.get("location"):
        event["location"] = event_data["location"]
    if event_data.get("description"):
        event["description"] = event_data["description"]
    attendees = event_data.get("attendees", [])
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]

    try:
        created_event = (
            service.events()
            .insert(calendarId="primary", body=event)
            .execute()
        )
    except HttpError as e:
        raise Exception(f"Google Calendar API error {e.status_code}: {e.reason}") from e

    return created_event