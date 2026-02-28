from fastapi import APIRouter, Request
from auth.oauth import oauth

router = APIRouter()

@router.get("/login/google")
async def login_via_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    
    # user contains:
    # user["email"]
    # user["name"]
    # user["picture"]

    return {
        "email": user["email"],
        "name": user["name"]
    }