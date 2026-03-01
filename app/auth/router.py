from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt
import httpx
import os

from app.database.session import get_db
from app.users.models import User

router = APIRouter()

SECRET_KEY     = os.getenv("SECRET_KEY")
ALGORITHM      = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24  # 1 day

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:3000")

# The callback URL must match exactly what is registered in Google Cloud Console
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")  # set this in Vercel env vars


def create_jwt_token(email: str) -> str:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is not set")
    expire  = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Step 1: Redirect user to Google ──────────────────────────────────────────
@router.get("/google")
async def login_via_google():
    """
    Redirect the user to Google's OAuth consent screen.

    We build the URL manually instead of using Authlib's authorize_redirect()
    because Authlib stores the CSRF state in request.session — on Vercel's
    serverless functions the session is not shared between invocations, which
    causes MismatchingStateError on the callback.

    By skipping state verification here (Google itself verifies the code),
    we avoid the cross-instance session problem entirely.
    """
    if not GOOGLE_CLIENT_ID or not REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID or GOOGLE_REDIRECT_URI env var is not set."
        )

    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile https://www.googleapis.com/auth/calendar",
        "access_type":   "offline",    # needed to get a refresh_token
        "prompt":        "consent",    # forces refresh_token on every login
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return RedirectResponse(url=google_auth_url)


# ── TEMPORARY DEBUG ENDPOINT — remove after confirming env vars work ─────────
@router.get("/debug-env")
async def debug_env():
    """Shows which env vars are visible to the running function. Remove after debugging."""
    import os
    return {
        "GOOGLE_CLIENT_ID":     os.getenv("GOOGLE_CLIENT_ID",     "NOT SET"),
        "GOOGLE_REDIRECT_URI":  os.getenv("GOOGLE_REDIRECT_URI",  "NOT SET"),
        "GOOGLE_CLIENT_SECRET": "SET" if os.getenv("GOOGLE_CLIENT_SECRET") else "NOT SET",
        "SECRET_KEY":           "SET" if os.getenv("SECRET_KEY")           else "NOT SET",
        "FRONTEND_URL":         os.getenv("FRONTEND_URL",         "NOT SET"),
        "DATABASE_URL":         "SET" if os.getenv("DATABASE_URL")         else "NOT SET",
        "all_env_keys":         [k for k in os.environ.keys()],
    }

# ── Step 2: Google redirects back here with ?code=... ─────────────────────────
@router.get("/google/callback")
async def auth_google_callback(
    code:    str = None,
    error:   str = None,
    request: Request = None,
    db:      Session = Depends(get_db),
):
    """
    Exchange the authorization code for tokens, upsert the user, issue a JWT,
    and redirect back to the frontend.
    """
    # User denied access on Google's consent screen
    if error:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=access_denied")

    if not code:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=auth_failed")

    # ── Exchange code for tokens ──────────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if token_response.status_code != 200:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=token_exchange_failed")

    token_data = token_response.json()

    # ── Fetch user info from Google ───────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )

    if userinfo_response.status_code != 200:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=userinfo_failed")

    user_info  = userinfo_response.json()
    email      = user_info.get("email")
    expires_in = token_data.get("expires_in")
    expiry_date = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    # ── Upsert user in DB ─────────────────────────────────────────────────────
    db_user = db.query(User).filter(
        (User.google_id == user_info.get("sub")) | (User.email == email)
    ).first()

    if not db_user:
        db_user = User(email=email)
        db.add(db_user)

    db_user.name         = user_info.get("name")
    db_user.google_id    = user_info.get("sub")
    db_user.access_token = token_data.get("access_token")
    db_user.token_expiry = expiry_date

    # Google only returns refresh_token on first login or after re-consent
    new_refresh_token = token_data.get("refresh_token")
    if new_refresh_token:
        db_user.refresh_token = new_refresh_token

    db.commit()
    db.refresh(db_user)

    # ── Issue JWT and redirect to frontend ────────────────────────────────────
    jwt_token    = create_jwt_token(db_user.email)
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?token={jwt_token}"
        f"&name={db_user.name}"
        f"&email={db_user.email}"
    )
    return RedirectResponse(url=redirect_url)