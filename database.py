import os
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, text
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = Path(__file__).resolve().parent

# Local dev default: a SQLite file next to this module.
_DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'expense.db').as_posix()}"

DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_SQLITE_URL)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

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


def get_vietnam_time() -> datetime:
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_database_multi_tenant():
    """Performs safe, idempotent schema migrations for multi-tenancy on both SQLite and PostgreSQL.

    1. Adds missing columns (e.g. `destination_wallet` in expenses).
    2. Ensures `users` table exists.
    3. Creates default `admin` user if no users exist, preserving all previous records.
    4. Adds `user_id` column to all data tables and backfills old rows to default admin.
    5. Migrates category constraint from UNIQUE(name) to UNIQUE(user_id, name).
    """
    from auth import hash_password

    with engine.begin() as conn:
        # 1. Destination wallet in expenses
        if IS_SQLITE:
            exp_exists = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'")
            ).fetchone()
            if exp_exists:
                cols = [r[1] for r in conn.execute(text("PRAGMA table_info(expenses)")).fetchall()]
                if "destination_wallet" not in cols:
                    conn.execute(text("ALTER TABLE expenses ADD COLUMN destination_wallet VARCHAR(50) NULL"))
        else:
            col_exists = conn.execute(
                text("SELECT 1 FROM information_schema.columns WHERE table_name='expenses' AND column_name='destination_wallet'")
            ).fetchone()
            if not col_exists:
                conn.execute(text("ALTER TABLE expenses ADD COLUMN destination_wallet VARCHAR(50) NULL"))

        # 2. Ensure `users` table exists
        if IS_SQLITE:
            users_table_exists = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            ).fetchone()
            if not users_table_exists:
                conn.execute(text("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username VARCHAR(100) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP NOT NULL
                    )
                """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
            """))

        # 3. Check / create default admin user
        default_user = conn.execute(text("SELECT id, username FROM users ORDER BY id ASC LIMIT 1")).fetchone()
        if not default_user:
            admin_username = "admin"
            env_pwd = os.environ.get("DEFAULT_ADMIN_PASSWORD")
            if env_pwd:
                admin_pwd = env_pwd
            else:
                admin_pwd = secrets.token_urlsafe(12)

            pwd_hash = hash_password(admin_pwd)
            now_str = get_vietnam_time()

            conn.execute(
                text("INSERT INTO users (username, password_hash, created_at) VALUES (:u, :p, :c)"),
                {"u": admin_username, "p": pwd_hash, "c": now_str}
            )
            default_user = conn.execute(text("SELECT id, username FROM users WHERE username = :u"), {"u": admin_username}).fetchone()

            print("\n" + "=" * 72)
            print("[MULTI-TENANT SETUP] Default administrator account initialized:")
            print(f"   Username: {admin_username}")
            print(f"   Password: {admin_pwd}")
            print("   -> Use this account to log in and access all pre-existing data.")
            print("=" * 72 + "\n")

        default_user_id = default_user[0]

        # 4. Add user_id column and backfill in all entity tables
        entity_tables = ["expenses", "categories", "budgets", "recurring_transactions", "notes", "day_counters"]
        for tbl in entity_tables:
            if IS_SQLITE:
                t_exists = conn.execute(
                    text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl}'")
                ).fetchone()
                if not t_exists:
                    continue
                cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({tbl})")).fetchall()]
                if "user_id" not in cols:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER NULL"))
            else:
                t_exists = conn.execute(
                    text(f"SELECT 1 FROM information_schema.tables WHERE table_name='{tbl}'")
                ).fetchone()
                if not t_exists:
                    continue
                c_exists = conn.execute(
                    text(f"SELECT 1 FROM information_schema.columns WHERE table_name='{tbl}' AND column_name='user_id'")
                ).fetchone()
                if not c_exists:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER NULL"))

            # Backfill existing rows without user_id
            conn.execute(
                text(f"UPDATE {tbl} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": default_user_id}
            )

        # 5. Migrate categories unique constraint to (user_id, name)
        if IS_SQLITE:
            cat_row = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='categories'")
            ).fetchone()
            if cat_row and "UNIQUE (name)" in cat_row[0]:
                conn.execute(text("""
                    CREATE TABLE categories_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        type VARCHAR(20) NOT NULL,
                        CONSTRAINT uq_user_category_name UNIQUE (user_id, name)
                    )
                """))
                conn.execute(text("""
                    INSERT INTO categories_new (id, user_id, name, type)
                    SELECT id, user_id, name, type FROM categories
                """))
                conn.execute(text("DROP TABLE categories"))
                conn.execute(text("ALTER TABLE categories_new RENAME TO categories"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_id ON categories (id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_user_id ON categories (user_id)"))
        else:
            # PostgreSQL: drop old unique constraint if present, add composite unique index
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE table_name = 'categories' AND constraint_name = 'categories_name_key'
                    ) THEN
                        ALTER TABLE categories DROP CONSTRAINT categories_name_key;
                    END IF;
                END $$;
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_category_name ON categories (user_id, name);
            """))