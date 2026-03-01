from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.security import get_current_user
from app.users.models import User
from app.users.schemas import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
def get_me(
    current_user: User = Depends(get_current_user),  # JWT replaces request.session
):
    """Return the profile of the currently authenticated user."""
    return current_user


@router.get("/{user_id}", response_model=UserRead)
def get_user_by_id(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch any user by ID. Only accessible to authenticated users."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user