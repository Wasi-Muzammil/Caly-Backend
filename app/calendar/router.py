from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.users.models import User
from app.core.security import get_current_user
from app.calendar.service import get_calendar_service, fetch_events, create_event
from app.calendar.schemas import CreateEventRequest

router = APIRouter(
    prefix="/calendar",
    tags=["Calendar"],
)


def _get_service_and_sync_token(current_user: User, db: Session):
    """
    Build the Google Calendar service for this user and persist any
    refreshed access token back to the database.
    """
    service, creds = get_calendar_service(
        access_token=current_user.access_token,
        refresh_token=current_user.refresh_token,
        token_expiry=current_user.token_expiry,   # required so the library knows when to refresh
    )

    # If the library silently refreshed the token, save the new values.
    if creds.token != current_user.access_token:
        current_user.access_token = creds.token
        # Also update the expiry so we don't refresh on every single request.
        if creds.expiry:
            current_user.token_expiry = creds.expiry
        db.commit()

    return service


@router.get("/events")
def get_user_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.access_token:
        raise HTTPException(status_code=400, detail="Google account not connected")

    service = _get_service_and_sync_token(current_user, db)
    events = fetch_events(service)
    return {"events": events}


@router.post("/create")
def create_user_event(
    request: CreateEventRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.access_token:
        raise HTTPException(status_code=400, detail="Google account not connected")

    service = _get_service_and_sync_token(current_user, db)
    event = create_event(service, request.dict())

    return {
        "message": "Event created successfully",
        "event_link": event.get("htmlLink"),
    }