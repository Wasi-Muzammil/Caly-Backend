from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import List
from datetime import datetime

class SuggestRequest(BaseModel):
    participants: List[EmailStr]
    duration_minutes: int = Field(15, ge=15, le=480)
    start_date: datetime
    end_date: datetime
    is_priority: bool = False
    timezone: str = "UTC" 

    # Logic check: Make sure end_date is after start_date
    @model_validator(mode='after')
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self

class Slot(BaseModel):
    start: datetime
    end: datetime
    score: int = Field(..., ge=0, le=100) 

class SuggestResponse(BaseModel):
    slots: List[Slot]
    warnings: List[str] = [] 

class ConfirmRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    start: datetime
    duration_minutes: int = Field(..., ge=1)
    participants: List[EmailStr]
    is_priority: bool = False
