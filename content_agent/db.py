"""Postgres access for graph nodes.

The API opens its own pool in its lifespan (that pool also serves the checkpointer).
Graph nodes can't reach it, so they use this small pool instead. It is created the
first time a node asks for it and reused after that, the same way get_llm works.
"""
import os
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://agent:agent@localhost:5432/content_agent")


@lru_cache(maxsize=None)
def get_pool() -> ConnectionPool:
    """The graph's pool: created and opened on the first call, the same pool after that."""
    pool = ConnectionPool(
        DATABASE_URL,
        kwargs={
            "autocommit": True,         # each statement commits on its own, like the API pool
            "prepare_threshold": 0,     # no server-side prepared statements (safe behind pgbouncer)
            "row_factory": dict_row,    # rows come back as dicts: row["draft"]
        },
        min_size=1,                     # the default min_size is 4, which is more than max_size
        max_size=2,                     # the publisher writes one row per run
        check=ConnectionPool.check_connection,   # replace connections a Postgres restart killed
        open=False,
    )
    pool.open(wait=True, timeout=10)    # fail now if Postgres is down, not on the first query
    return pool


def close_pool() -> None:
    """Close the pool if a node ever opened it. Safe to call more than once."""
    if get_pool.cache_info().currsize:  # 0 means get_pool() was never called
        get_pool().close()
        get_pool.cache_clear()          # a later get_pool() builds a fresh pool
