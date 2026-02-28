from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import datetime
import os


def get_calendar_service(access_token: str, refresh_token: str, token_expiry=None):
    """
    Build and return an authenticated Google Calendar service.

    token_expiry: datetime from the DB (optional) — used to detect whether
                  the access token is expired so it can be refreshed proactively.
    """
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        expiry=token_expiry,
    )

    # Refresh the access token if it has expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("calendar", "v3", credentials=creds)
    return service, creds


def fetch_events(service):
    """Fetch the next 10 upcoming events from the user's primary calendar."""
    now = datetime.datetime.utcnow().isoformat() + "Z"

    event_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=10,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return event_result.get("items", [])


def create_event(service, event_data: dict):
    """
    Insert a new event into the user's primary calendar.

    Builds the event body carefully to avoid sending null/None values
    which cause Google API to return 400 Bad Request.
    """

    # --- Required fields ---
    event = {
        "summary": event_data["summary"],
        "start": {
            "dateTime": event_data["start_time"],  # Must be RFC 3339: 2024-01-15T10:00:00+05:00
            "timeZone": event_data["timezone"],
        },
        "end": {
            "dateTime": event_data["end_time"],    # Must be RFC 3339: 2024-01-15T11:00:00+05:00
            "timeZone": event_data["timezone"],
        },
    }

    # --- Optional fields: only add if they have actual values ---
    # Sending None/null for these fields causes Google to return 400 Bad Request
    if event_data.get("location"):
        event["location"] = event_data["location"]

    if event_data.get("description"):
        event["description"] = event_data["description"]

    attendees = event_data.get("attendees", [])
    if attendees:
        event["attendees"] = [{"email": email} for email in attendees]

    # --- Send to Google ---
    try:
        created_event = (
            service.events()
            .insert(calendarId="primary", body=event)
            .execute()
        )
    except HttpError as e:
        # Surface a clear error with the exact detail Google returned
        raise Exception(f"Google Calendar API error {e.status_code}: {e.reason}") from e

    return created_event