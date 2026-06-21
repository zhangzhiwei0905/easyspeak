"""EasySpeak - English Oral Practice Mini Program Backend"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import engine, Base
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

settings = get_settings()


def _ensure_word_enrichment_columns():
    """Add new nullable word enrichment columns for existing non-migrated DBs."""
    inspector = inspect(engine)
    if "words" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("words")}
    missing = [
        column for column in ("usage_note", "context_meanings")
        if column not in existing
    ]
    if not missing:
        return

    with engine.begin() as conn:
        for column in missing:
            try:
                conn.execute(text(f"ALTER TABLE words ADD COLUMN {column} TEXT"))
            except SQLAlchemyError as exc:
                # Multiple uvicorn workers can race during first deploy. Re-check
                # before surfacing the error so startup remains idempotent.
                refreshed = {
                    col["name"] for col in inspect(conn).get_columns("words")
                }
                if column not in refreshed:
                    raise exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create all tables if they don't exist."""
    # Import all models to register them with Base
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_word_enrichment_columns()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from app.routers import daily, auth, review, quiz, admin, learn, user

    app.include_router(daily.router, prefix="/api/v1/daily", tags=["daily"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(review.router, prefix="/api/v1/review", tags=["review"])
    app.include_router(quiz.router, prefix="/api/v1/quiz", tags=["quiz"])
    app.include_router(learn.router, prefix="/api/v1/learn", tags=["learn"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(user.router, prefix="/api/v1/user", tags=["user"])

    @app.get("/api/v1/health")
    async def health_check():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
