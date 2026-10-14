import os
import re
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

# Importing the database module must not connect to or migrate the real database.
with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:", "SECRET_KEY": "migration-test-secret"}):
    import database
    import auth


class MigrationTests(unittest.TestCase):
    def test_sqlite_migration_and_restart_preserve_private_categories(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, created_at TIMESTAMP NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO users VALUES (1, 'admin', 'hash', '2026-01-01')
            """))
            connection.execute(text("""
                CREATE TABLE categories (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    name TEXT NOT NULL, type TEXT NOT NULL,
                    UNIQUE (user_id, name)
                )
            """))
            connection.execute(text("""
                INSERT INTO categories VALUES (1, 1, 'Lương Ameno', 'income')
            """))
            connection.execute(text("""
                INSERT INTO categories VALUES (2, 1, 'Lương riêng', 'income')
            """))

        with patch.object(database, "engine", engine), patch.object(database, "IS_SQLITE", True):
            database.migrate_database_multi_tenant()
            with engine.connect() as connection:
                first = connection.execute(text(
                    "SELECT id, user_id, is_shared, name, type FROM categories ORDER BY id"
                )).fetchall()
            database.migrate_database_multi_tenant()
            with engine.connect() as connection:
                second = connection.execute(text(
                    "SELECT id, user_id, is_shared, name, type FROM categories ORDER BY id"
                )).fetchall()

        self.assertEqual(first, second)
        shared = [row for row in second if row.is_shared]
        private = [row for row in second if not row.is_shared]
        self.assertEqual(len(shared), 13)
        self.assertTrue(all(row.user_id is None for row in shared))
        self.assertEqual([(row.id, row.user_id, row.name) for row in private], [(2, 1, "Lương riêng")])

    def test_postgresql_first_migration_uses_boolean_literals(self):
        connection = PostgreSQLConnection(has_scope=False)
        with patch.object(database, "engine", PostgreSQLEngine(connection)), patch.object(database, "IS_SQLITE", False):
            database.migrate_database_multi_tenant()

        deletes = [sql for sql in connection.statements if "DELETE FROM categories" in sql]
        self.assertEqual(len(deletes), 13)
        self.assertTrue(all("is_shared = FALSE" in sql for sql in deletes))
        inserts = [sql for sql in connection.statements if "INSERT INTO categories" in sql]
        self.assertEqual(len(inserts), 13)
        self.assertTrue(all("VALUES (NULL, TRUE" in sql for sql in inserts))

    def test_postgresql_restart_does_not_backfill_shared_owners(self):
        connection = PostgreSQLConnection(has_scope=True)
        with patch.object(database, "engine", PostgreSQLEngine(connection)), patch.object(database, "IS_SQLITE", False):
            database.migrate_database_multi_tenant()

        backfills = [sql for sql in connection.statements if "UPDATE categories" in sql]
        self.assertEqual(len(backfills), 1)
        self.assertIn("user_id IS NULL AND is_shared = FALSE", backfills[0])
        self.assertFalse(any("DELETE FROM categories" in sql for sql in connection.statements))


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class PostgreSQLConnection:
    """Capture both PostgreSQL migration paths without needing a live server."""
    def __init__(self, has_scope):
        self.has_scope = has_scope
        self.statements = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append(sql)
        if re.search(r"\bis_shared\s*=\s*[01]\b", sql, re.IGNORECASE):
            raise AssertionError("PostgreSQL cannot compare a boolean column with an integer")
        if "SELECT id, username FROM users" in sql:
            return Result([(1, "admin")])
        if "information_schema.tables" in sql:
            return Result([(1,)] if "table_name='categories'" in sql else [])
        if "SELECT column_name" in sql:
            columns = ["id", "user_id", "name", "type"]
            if self.has_scope:
                columns.append("is_shared")
            return Result([(column,) for column in columns])
        if "information_schema.columns" in sql:
            if "table_name='expenses'" in sql:
                return Result([(1,)])
            return Result([(1,)] if self.has_scope else [])
        return Result([])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PostgreSQLEngine:
    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return self.connection


if __name__ == "__main__":
    unittest.main()
