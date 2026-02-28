from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from auth.router import router as auth_router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY")  # must be strong & random
)

app.include_router(auth_router)