import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

from app.auth.router import router as auth_router
from app.meetings.router import router as meetings_router
from app.users.router import router as user_router
from app.calendar.router import router as calendar_router

from app.database.base import Base
from app.database.session import engine

load_dotenv()

app = FastAPI(title="Caly-Backend")

# CORS — allows your frontend to make requests to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten to your frontend URL in production e.g. ["https://yourapp.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware is still required for Google OAuth callback flow (Authlib uses request.session internally)
# After the callback, the JWT is issued and all subsequent requests use only the JWT header
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY")
)


@app.on_event("startup")
def startup():
    # This creates your database tables automatically when the app starts
    from app.users import models
    from app.meetings import models
    Base.metadata.create_all(bind=engine)


app.include_router(auth_router,     prefix="/auth")
app.include_router(meetings_router, prefix="/meeting")
app.include_router(user_router,     prefix="/users")
app.include_router(calendar_router)


@app.get("/", tags=["home"])
async def home():
    return {
        "status": "online",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "message": "Welcome to Caly Backend"
    }