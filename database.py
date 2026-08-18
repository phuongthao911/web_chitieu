import os
from pathlib import Path

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker, declarative_base


BASE_DIR = Path(__file__).resolve().parent

# Local dev default: a SQLite file next to this module.
_DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'expense.db').as_posix()}"

# In production, set the DATABASE_URL environment variable (e.g. on
# Railway/Render this is provided automatically when you attach a
# Postgres database). If it's not set, we fall back to local SQLite
# so nothing changes for local development.
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE_URL)

# Some hosts (Heroku-style) hand out URLs starting with "postgres://",
# but SQLAlchemy 2.x requires the "postgresql://" scheme. Normalize it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# "check_same_thread" is a SQLite-only quirk; Postgres doesn't need it.
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_expenses_table_if_needed():
    """Dynamically adds missing columns to `expenses` table on both SQLite and Postgres.

    This ensures safe database migrations on Production (Supabase) without losing data.
    """
    with engine.begin() as connection:
        if IS_SQLITE:
            table_exists = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
            ).fetchone()
            if not table_exists:
                return
            
            # Fetch existing columns
            columns = [row[1] for row in connection.execute(text("PRAGMA table_info(expenses)"))]
            
            # Dynamically add missing columns
            if "destination_wallet" not in columns:
                connection.execute(text("ALTER TABLE expenses ADD COLUMN destination_wallet VARCHAR(50) NULL"))
        else:
            # PostgreSQL migration
            # We can use standard information_schema queries to inspect and add columns
            column_exists = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='expenses' AND column_name='destination_wallet'"
                )
            ).fetchone()
            
            if not column_exists:
                connection.execute(text("ALTER TABLE expenses ADD COLUMN destination_wallet VARCHAR(50) NULL"))