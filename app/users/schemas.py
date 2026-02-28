from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: Optional[str] = None
    created_at: datetime 
    model_config = ConfigDict(from_attributes=True)

class UserSession(BaseModel):
    """A smaller schema specifically for what we store in the session"""
    email: EmailStr
    name: Optional[str] = None