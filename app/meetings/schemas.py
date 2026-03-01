from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import List, Optional
from datetime import datetime, timezone
import pytz


def _ensure_timezone_aware(value: datetime, field_name: str) -> datetime:
    """
    Reject naive datetimes (no UTC offset).
    A naive datetime like '2024-01-15T12:00:00' has no offset so the backend
    cannot know what UTC time it represents — this is the root cause of the
    Google Calendar time mismatch bug.

    Always send datetimes WITH an offset, e.g. '2024-01-15T12:00:00+05:00'
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"'{field_name}' must include a UTC offset. "
            f"Example for Karachi: 2024-01-15T12:00:00+05:00  "
            f"Example for UTC:     2024-01-15T12:00:00+00:00"
        )
    return value


def _to_utc(value: datetime) -> datetime:
    """Convert any timezone-aware datetime to UTC for consistent DB storage."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)  # store as naive UTC in DB


# ─────────────────────────────────────────────
# Suggest (Step 1 — find slots)
# ─────────────────────────────────────────────

class SuggestRequest(BaseModel):
    participants:     List[EmailStr]
    duration_minutes: int      = Field(30, ge=15, le=480)
    start_date:       datetime
    end_date:         datetime
    is_priority:      bool     = False
    timezone:         str      = "UTC"
    max_slots:        int      = Field(10, ge=1, le=50)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def require_offset(cls, v, info):
        dt = datetime.fromisoformat(str(v)) if isinstance(v, str) else v
        return _ensure_timezone_aware(dt, info.field_name)

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        window_days = (self.end_date - self.start_date).days
        if window_days > 30:
            raise ValueError("Search window cannot exceed 30 days")
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "participants":     ["alice@example.com", "bob@example.com"],
                "duration_minutes": 60,
                # ✅ Always include the UTC offset — +05:00 for Karachi
                "start_date":       "2024-01-15T08:00:00+05:00",
                "end_date":         "2024-01-19T18:00:00+05:00",
                "is_priority":      False,
                "timezone":         "Asia/Karachi",
                "max_slots":        5,
            }
        }


class SlotResult(BaseModel):
    start:              datetime
    end:                datetime
    score:              int = Field(..., ge=0, le=100)
    free_count:         int
    total_participants: int
    all_free:           bool


class SuggestResponse(BaseModel):
    slots:    List[SlotResult]
    warnings: List[str] = []


# ─────────────────────────────────────────────
# Confirm (Step 2 — book a slot)
# ─────────────────────────────────────────────

class ConfirmRequest(BaseModel):
    title:            str           = Field(..., min_length=1, max_length=100)
    start:            datetime
    duration_minutes: int           = Field(..., ge=1)
    participants:     List[EmailStr]
    is_priority:      bool          = False
    description:      Optional[str] = None
    location:         Optional[str] = None
    timezone:         str           = "UTC"

    @field_validator("start", mode="before")
    @classmethod
    def require_offset(cls, v):
        dt = datetime.fromisoformat(str(v)) if isinstance(v, str) else v
        return _ensure_timezone_aware(dt, "start")

    class Config:
        json_schema_extra = {
            "example": {
                "title":            "Sprint Planning",
                # ✅ +05:00 offset tells the backend this is Karachi local time
                "start":            "2024-01-15T12:00:00+05:00",
                "duration_minutes": 60,
                "participants":     ["alice@example.com", "bob@example.com"],
                "is_priority":      False,
                "timezone":         "Asia/Karachi",
            }
        }


class MeetingResponse(BaseModel):
    id:           str
    title:        str
    start:        datetime
    end:          datetime
    is_priority:  bool
    status:       str
    created_by:   str
    participants: List[str]


# ─────────────────────────────────────────────
# Availability Timeline (Visual)
# ─────────────────────────────────────────────

class AvailabilityRequest(BaseModel):
    participants: List[EmailStr]
    date:         datetime
    timezone:     str = "UTC"   # used to scope the day correctly per user's local timezone

    @field_validator("date", mode="before")
    @classmethod
    def require_offset(cls, v):
        dt = datetime.fromisoformat(str(v)) if isinstance(v, str) else v
        return _ensure_timezone_aware(dt, "date")

    class Config:
        json_schema_extra = {
            "example": {
                "participants": ["alice@example.com", "bob@example.com"],
                # ✅ Include offset so day boundaries are computed correctly
                "date":         "2024-01-15T00:00:00+05:00",
                "timezone":     "Asia/Karachi",
            }
        }


class ParticipantTimeline(BaseModel):
    email:       str
    busy_blocks: List[dict]


class AvailabilityResponse(BaseModel):
    date:         str
    participants: List[ParticipantTimeline]
    warnings:     List[str] = []