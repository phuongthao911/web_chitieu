import os
from pathlib import Path

from sqlalchemy import create_engine, text
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
    """Drops the `expenses` table if its schema is stale AND it's empty.

    This is a lightweight dev convenience for SQLite only — it relies on
    sqlite_master/PRAGMA, which don't exist on Postgres. On Postgres,
    use a real migration tool (e.g. Alembic) instead, so this function
    is a no-op there.
    """
    if not IS_SQLITE:
        return

    with engine.begin() as connection:
        table_exists = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
        ).fetchone()

        if not table_exists:
            return

        columns = [row[1] for row in connection.execute(text("PRAGMA table_info(expenses)"))]
        desired_columns = [
            "id",
            "transaction_type",
            "amount",
            "category",
            "wallet",
            "note",
            "created_at",
        ]

        if columns != desired_columns:
            row_count = connection.execute(text("SELECT COUNT(*) FROM expenses")).scalar_one()

            if row_count == 0:
                connection.execute(text("DROP TABLE expenses"))