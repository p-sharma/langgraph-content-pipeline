"""The runs table: one row per run, written by the API.

Graph state lives in the checkpointer's tables, keyed by thread_id = run_id.
This table holds only what the checkpointer cannot: the run before its first
checkpoint, a crash, and (later) a cheap way to list runs. Status is never
stored here; the API works it out from the checkpoint.
"""
from datetime import datetime
from typing import TypedDict
from uuid import UUID

from psycopg_pool import ConnectionPool

MAX_ERROR_LENGTH = 2000

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    topic      text        NOT NULL,
    guidance   text,
    created_at timestamptz NOT NULL DEFAULT now(),
    error      text        -- set when the background run crashed
)"""

# run_id::text so callers get a plain string, the same type as the thread_id
COLUMNS = "run_id::text AS run_id, topic, guidance, created_at, error"


class RunRow(TypedDict):
    run_id: str
    topic: str
    guidance: str | None
    created_at: datetime
    error: str | None


def create_table(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute(CREATE_TABLE)


def insert_run(pool: ConnectionPool, topic: str, guidance: str | None) -> RunRow:
    with pool.connection() as conn:
        return conn.execute(
            f"INSERT INTO runs (topic, guidance) VALUES (%s, %s) RETURNING {COLUMNS}",
            (topic, guidance),
        ).fetchone()


def get_run(pool: ConnectionPool, run_id: UUID) -> RunRow | None:
    with pool.connection() as conn:
        return conn.execute(f"SELECT {COLUMNS} FROM runs WHERE run_id = %s", (run_id,)).fetchone()


def set_error(pool: ConnectionPool, run_id: str, error: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE runs SET error = %s WHERE run_id = %s",
            (error[:MAX_ERROR_LENGTH], run_id),
        )
