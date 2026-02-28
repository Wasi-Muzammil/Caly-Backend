import os

from fastapi import FastAPI
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

app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SECRET_KEY", "temporary-secret-key")
)

@app.on_event("startup")
def startup():
    # This creates your database tables automatically when the app starts
    from app.users import models
    from app.meetings import models
    Base.metadata.create_all(bind=engine)
    
app.include_router(auth_router, prefix="/auth")
app.include_router(meetings_router, prefix="/meeting")
app.include_router(user_router, prefix="/users")
app.include_router(calendar_router, prefix="/calendar")


@app.get("/", tags=["home"])
async def home():
    return {
        "status": "online",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "message": "Welcome to Caly Backend"
    }