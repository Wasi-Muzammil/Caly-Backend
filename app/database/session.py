import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# 1. Load configuration
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./caly.db")

# 2. Setup the Engine
# SQLite needs 'check_same_thread: False', but PostgreSQL/MySQL do not.
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# 3. Create a Session factory
# This is like a 'template' for creating new database connections
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. The Database Dependency
def get_db():
    """
    Creates a new database session for a single request 
    and closes it when the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
