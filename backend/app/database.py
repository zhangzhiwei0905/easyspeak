"""Database connection and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
}

if not settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    })

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
