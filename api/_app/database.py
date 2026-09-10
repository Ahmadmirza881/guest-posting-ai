"""Database configuration and session management for Guest Posting AI."""

from typing import Generator
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


from sqlalchemy.pool import NullPool

# Determine engine parameters based on database dialect
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False, "timeout": 30.0} if is_sqlite else {}

# Initialize SQLAlchemy Engine
if is_sqlite:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args=connect_args
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=40,
        pool_pre_ping=True,
    )

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a transactional database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None):
    """Create all database tables and ensure schema columns are up to date."""
    import app.models  # noqa: F401 - Ensure all models are imported before creating tables
    active_engine = target_engine or engine
    Base.metadata.create_all(bind=active_engine)

    # Safe lightweight schema synchronization for SQLite columns
    try:
        inspector = inspect(active_engine)
        table_names = inspector.get_table_names()

        with active_engine.connect() as conn:
            # Sync websites table
            if "websites" in table_names:
                web_cols = {col["name"] for col in inspector.get_columns("websites")}
                new_web_cols = [
                    ("crawl_status", "VARCHAR(50) DEFAULT 'pending'"),
                    ("last_crawled_at", "TIMESTAMP"),
                    ("http_status", "INTEGER"),
                    ("final_url", "TEXT"),
                    ("content_type", "VARCHAR(100)"),
                    ("html_content", "TEXT"),
                ]
                for col_name, col_type in new_web_cols:
                    if col_name not in web_cols:
                        conn.execute(text(f"ALTER TABLE websites ADD COLUMN {col_name} {col_type}"))

            # Sync guest_post_information table
            if "guest_post_information" in table_names:
                gp_cols = {col["name"] for col in inspector.get_columns("guest_post_information")}
                new_gp_cols = [
                    ("verification_status", "VARCHAR(50) DEFAULT 'unverified'"),
                    ("ai_confidence", "INTEGER"),
                    ("ai_reason", "TEXT"),
                    ("ai_evidence", "TEXT"),
                    ("verified_at", "TIMESTAMP"),
                ]
                for col_name, col_type in new_gp_cols:
                    if col_name not in gp_cols:
                        conn.execute(text(f"ALTER TABLE guest_post_information ADD COLUMN {col_name} {col_type}"))

            # Sync website_analyses table (Step 16 & 17)
            if "website_analyses" in table_names:
                wa_cols = {col["name"] for col in inspector.get_columns("website_analyses")}
                new_wa_cols = [
                    ("primary_niche", "VARCHAR(255)"),
                    ("topics", "TEXT"),
                    ("niche_confidence", "INTEGER"),
                    ("relevance_score", "INTEGER"),
                    ("relevance_reason", "TEXT"),
                    ("content_quality_score", "INTEGER"),
                    ("content_quality_reason", "TEXT"),
                    ("trust_signals", "TEXT"),
                    ("editorial_standards", "TEXT"),
                    ("strengths", "TEXT"),
                    ("weaknesses", "TEXT"),
                    ("analysis_evidence", "TEXT"),
                    ("warnings", "TEXT"),
                    ("analysis_confidence", "INTEGER"),
                    ("analysis_status", "VARCHAR(50) DEFAULT 'completed'"),
                    ("score_breakdown", "TEXT"),
                    ("scoring_status", "VARCHAR(50) DEFAULT 'pending'"),
                    ("scored_at", "TIMESTAMP"),
                ]
                for col_name, col_type in new_wa_cols:
                    if col_name not in wa_cols:
                        conn.execute(text(f"ALTER TABLE website_analyses ADD COLUMN {col_name} {col_type}"))

            # Sync users table (Step 21)
            if "users" in table_names:
                user_cols = {col["name"] for col in inspector.get_columns("users")}
                if "password_hash" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))

            # Sync saved_websites table (Step 21)
            if "saved_websites" in table_names:
                saved_cols = {col["name"] for col in inspector.get_columns("saved_websites")}
                if "user_id" not in saved_cols:
                    conn.execute(text("ALTER TABLE saved_websites ADD COLUMN user_id INTEGER REFERENCES users(id)"))

                # Drop obsolete Step 20 global unique index on website_id if present
                try:
                    conn.execute(text("DROP INDEX IF EXISTS ix_saved_websites_website_id"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_saved_websites_website_id ON saved_websites (website_id)"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_website_saved ON saved_websites (user_id, website_id)"))
                except Exception:
                    pass

            # Sync searches table (Step 22)
            if "searches" in table_names:
                search_cols = {col["name"] for col in inspector.get_columns("searches")}
                if "user_id" not in search_cols:
                    conn.execute(text("ALTER TABLE searches ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                try:
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_searches_user_id ON searches (user_id)"))
                except Exception:
                    pass

            conn.commit()
    except Exception:
        pass
