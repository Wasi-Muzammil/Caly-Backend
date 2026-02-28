from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.users.models import User
from app.users.schemas import UserRead

router = APIRouter()

@router.get("/me", response_model=UserRead)
async def get_me(request: Request, db: Session = Depends(get_db)):
    # 1. Get user info from the session
    session_user = request.session.get("user")
    
    if not session_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    # 2. Fetch the full user record from the DB using the email in the session
    db_user = db.query(User).filter(User.email == session_user["email"]).first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return db_user