from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime


class CreateEventRequest(BaseModel):
    summary: str
    location: Optional[str] = None
    description: Optional[str] = None
    start_time: str  # Must be RFC 3339 format: 2024-01-15T10:00:00+05:00
    end_time: str    # Must be RFC 3339 format: 2024-01-15T11:00:00+05:00
    timezone: str    # e.g. "Asia/Karachi", "America/New_York", "UTC"
    attendees: Optional[List[str]] = []

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_datetime_format(cls, value: str) -> str:
        """
        Ensure the datetime is in RFC 3339 format which Google Calendar requires.
        Valid:   2024-01-15T10:00:00+05:00
        Valid:   2024-01-15T10:00:00Z
        Invalid: 2024-01-15 10:00:00
        Invalid: 2024-01-15
        """
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"'{value}' is not a valid datetime. "
                "Use RFC 3339 format: YYYY-MM-DDTHH:MM:SS+HH:MM  "
                "Example: 2024-01-15T10:00:00+05:00"
            )
        return value

    @field_validator("end_time")
    @classmethod
    def end_must_be_after_start(cls, end_time: str, info) -> str:
        start_time = info.data.get("start_time")
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if end_dt <= start_dt:
                raise ValueError("end_time must be after start_time")
        return end_time

    class Config:
        json_schema_extra = {
            "example": {
                "summary": "Team Meeting",
                "location": "Office Room 1",
                "description": "Weekly sync",
                "start_time": "2024-01-15T10:00:00+05:00",
                "end_time": "2024-01-15T11:00:00+05:00",
                "timezone": "Asia/Karachi",
                "attendees": ["colleague@example.com"]
            }
        }