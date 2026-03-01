import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

# NeonDB provides a PostgreSQL connection string in this format:
# postgresql://user:password@host/dbname?sslmode=require
# SQLAlchemy requires "postgresql://" not "postgres://" (common Neon gotcha)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    # NeonDB (PostgreSQL) does not need check_same_thread.
    # pool_pre_ping=True reconnects dropped connections automatically —
    # important for serverless Neon which may close idle connections.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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