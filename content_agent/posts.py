"""The posts table: one row per published run.

Written by the publisher node, read by the archive endpoints. Every function takes
the pool to use: the publisher passes db.get_pool(), the API passes its own pool.
Rows are dicts because both pools use dict_row.
"""
from datetime import datetime
from typing import Literal, TypedDict

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

# run_id is the primary key: Postgres itself refuses a second post for the same run.
# "references" is quoted because REFERENCES is a reserved word in SQL.
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    run_id         text        PRIMARY KEY,
    topic          text        NOT NULL,
    draft          text        NOT NULL,
    "references"   jsonb       NOT NULL,
    critic_verdict text        NOT NULL,
    edited         boolean     NOT NULL,
    published_at   timestamptz NOT NULL DEFAULT now()
)"""
CREATE_INDEX = "CREATE INDEX IF NOT EXISTS posts_published_at ON posts (published_at DESC)"

COLUMNS = 'run_id, topic, draft, "references", critic_verdict, edited, published_at'


class NewPost(TypedDict):
    """What the publisher writes. published_at is left out: the database sets it."""
    run_id: str
    topic: str
    draft: str                 # text with [n] citation markers
    references: list[str]      # references[n-1] is the URL for [n]
    critic_verdict: Literal["passed", "not_reviewed", "budget_exhausted"]
    edited: bool               # an editor requested changes before approving


class PostRow(NewPost):
    """A stored post. Inherits every NewPost field."""
    published_at: datetime


def create_table(pool: ConnectionPool) -> None:
    with pool.connection() as conn:
        conn.execute(CREATE_TABLE)
        conn.execute(CREATE_INDEX)


def insert_post(pool: ConnectionPool, post: NewPost) -> bool:
    """Store the post. False if this run already has one; the stored post is left unchanged.

    ON CONFLICT DO NOTHING makes a replay safe: if the publisher runs twice for the
    same run (e.g. retried after a crash), the second insert is a no-op, not an error.
    """
    with pool.connection() as conn:
        cur = conn.execute(
            'INSERT INTO posts (run_id, topic, draft, "references", critic_verdict, edited) '
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (run_id) DO NOTHING",
            (
                post["run_id"],
                post["topic"],
                post["draft"],
                Jsonb(post["references"]),   # a plain list would be sent as a Postgres array
                post["critic_verdict"],
                post["edited"],
            ),
        )
        return cur.rowcount == 1


def list_posts(pool: ConnectionPool, limit: int, offset: int) -> list[PostRow]:
    """Newest first. run_id breaks ties, so pages never repeat or skip a post."""
    with pool.connection() as conn:
        return conn.execute(
            f"SELECT {COLUMNS} FROM posts ORDER BY published_at DESC, run_id LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()


def get_post(pool: ConnectionPool, run_id: str) -> PostRow | None:
    with pool.connection() as conn:
        return conn.execute(f"SELECT {COLUMNS} FROM posts WHERE run_id = %s", (run_id,)).fetchone()
