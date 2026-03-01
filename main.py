import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    allow_origins=["*"],        # tighten to your deployed frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware removed — it was only needed for Authlib's session-based
# OAuth state management. We now handle OAuth manually with httpx, which works
# correctly across Vercel's stateless serverless function invocations.


@app.on_event("startup")
def startup():
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