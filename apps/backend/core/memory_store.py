from __future__ import annotations

from collections.abc import Iterator

from langgraph.store.postgres import PostgresStore  # type: ignore[import-not-found]
import psycopg

from core.config import settings

_store_cm: Iterator[PostgresStore] | None = None
_store: PostgresStore | None = None


def _ensure_store_schema() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS store_migrations (
            v INTEGER PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS store (
            prefix text NOT NULL,
            key text NOT NULL,
            value jsonb NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prefix, key)
        )
        """,
        """
        ALTER TABLE store
        ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS ttl_minutes INT
        """,
    ]
    with psycopg.connect(settings.sync_database_uri) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
            cur.execute("INSERT INTO store_migrations (v) VALUES (0) ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO store_migrations (v) VALUES (1) ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO store_migrations (v) VALUES (2) ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO store_migrations (v) VALUES (3) ON CONFLICT DO NOTHING")


async def initialize_memory_store() -> PostgresStore:
    global _store_cm, _store
    if _store is not None:
        return _store

    _ensure_store_schema()
    _store_cm = PostgresStore.from_conn_string(settings.sync_database_uri)
    _store = _store_cm.__enter__()
    return _store


def get_memory_store() -> PostgresStore | None:
    return _store


async def shutdown_memory_store() -> None:
    global _store_cm, _store
    if _store_cm is not None:
        _store_cm.__exit__(None, None, None)
    _store_cm = None
    _store = None
