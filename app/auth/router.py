from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.oauth import oauth
from app.database.session import get_db
from app.users.models import User

router = APIRouter()


@router.get("/google")
async def login_via_google(request: Request):
    # This generates the Google Login URL and sends the user there
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    # 1. Get the token and user info from Google
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google")

    email = user_info.get("email")
    expires_in = token.get("expires_in")
    
    # Calculate when the token dies
    expiry_date = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    # 2. Look for existing user (Check Google ID first, then Email)
    db_user = db.query(User).filter(
        (User.google_id == user_info.get("sub")) | (User.email == email)
    ).first()

    # 3. Create or Update the user
    if not db_user:
        # Create a new user if they don't exist
        db_user = User(email=email)
        db.add(db_user)

    # Update the user's details (Sync with Google)
    db_user.name = user_info.get("name")
    db_user.google_id = user_info.get("sub")
    db_user.access_token = token.get("access_token")
    db_user.refresh_token = token.get("refresh_token")
    db_user.token_expiry = expiry_date

    # 4. Save to Database
    db.commit()
    db.refresh(db_user)

    try:
        request.session["user"] = {"id": db_user.id, "email": db_user.email, "name": db_user.name}
    except Exception:
        return {"message": "Login successful (session not stored)", "user": {"email": db_user.email, "name": db_user.name}}

    return {"message": "Login successful", "user": {"email": db_user.email, "name": db_user.name}}