from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from jose import jwt
import os

from app.auth.oauth import oauth
from app.database.session import get_db
from app.users.models import User

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 1 day


def create_jwt_token(email: str) -> str:
    """Create a signed JWT containing the user's email as the subject."""
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is not set")
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.get("/google")
async def login_via_google(request: Request):
    """Redirect the user to Google's OAuth consent screen."""
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/google/callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    # 1. Exchange the authorization code for tokens + user info
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to retrieve user info from Google")

    email = user_info.get("email")
    expires_in = token.get("expires_in")

    # Calculate when the Google access token expires
    expiry_date = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    # 2. Look up by Google ID first, fall back to email
    db_user = db.query(User).filter(
        (User.google_id == user_info.get("sub")) | (User.email == email)
    ).first()

    # 3. Create user if they don't exist yet
    if not db_user:
        db_user = User(email=email)
        db.add(db_user)

    # 4. Sync latest details from Google
    db_user.name = user_info.get("name")
    db_user.google_id = user_info.get("sub")
    db_user.access_token = token.get("access_token")
    db_user.token_expiry = expiry_date

    # Only overwrite the refresh token when Google actually returns one.
    # Google omits it on subsequent logins unless the user re-consents.
    new_refresh_token = token.get("refresh_token")
    if new_refresh_token:
        db_user.refresh_token = new_refresh_token

    # 5. Persist
    db.commit()
    db.refresh(db_user)

    # 6. Issue a JWT and redirect back to the frontend callback page.
    # The frontend reads the token from the URL, stores it, and navigates to /dashboard.
    # This is required because the OAuth flow happens entirely in the browser —
    # returning JSON here just leaves the user staring at a raw JSON page.
    jwt_token = create_jwt_token(db_user.email)

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url = (
        f"{frontend_url}/auth/callback"
        f"?token={jwt_token}"
        f"&name={db_user.name}"
        f"&email={db_user.email}"
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=redirect_url)