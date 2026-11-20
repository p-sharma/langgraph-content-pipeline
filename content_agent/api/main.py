import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from starlette.datastructures import State

from content_agent import posts
from content_agent.api import runs
from content_agent.api.active import ActiveRuns
from content_agent.api.schemas import (
    CreateRunRequest,
    PostOut,
    ResumeRequest,
    RunResponse,
    RunStatus,
)
from content_agent.api.status import derive_status, to_response
from content_agent.db import DATABASE_URL, close_pool
from content_agent.graph.builder import build_graph

logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNS = 4   # also keeps parallel LLM and Tavily calls under rate limits


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once: open the pool and build the graph at startup, close the pool at shutdown."""
    pool = ConnectionPool(
        DATABASE_URL,
        kwargs={
            "autocommit": True,         # PostgresSaver commits each write itself
            "prepare_threshold": 0,     # no server-side prepared statements (safe behind pgbouncer)
            "row_factory": dict_row,    # PostgresSaver reads rows as dicts; runs.py does too
        },
        max_size=10,
        check=ConnectionPool.check_connection,   # replace connections a Postgres restart killed
        open=False,
    )
    pool.open(wait=True, timeout=10)   # fail at startup if Postgres is down, not on the first request
    try:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()           # creates the checkpoint tables; safe on every start
        runs.create_table(pool)
        posts.create_table(pool)       # written by the publisher node, read by /posts
        app.state.pool = pool
        app.state.graph = build_graph(checkpointer=checkpointer)
        app.state.active = ActiveRuns()
        # Runs get their own threads: a minute-long run must not hold one of the
        # threads FastAPI uses to serve requests. Extra runs wait in the queue.
        app.state.executor = ThreadPoolExecutor(MAX_CONCURRENT_RUNS, thread_name_prefix="graph-run")
        yield
    finally:
        if hasattr(app.state, "executor"):
            # Don't wait for in-flight runs: they stop at their last checkpoint
            app.state.executor.shutdown(wait=False, cancel_futures=True)
        close_pool()                   # the graph's own pool, if the publisher ever opened it
        pool.close()


app = FastAPI(title="Content Agent API", lifespan=lifespan)


def _config(run_id: str) -> dict:
    """The run ID is the graph's thread_id: the key for every checkpoint of this run.
    The metadata tags the run's LangSmith traces with the same ID."""
    return {"configurable": {"thread_id": run_id}, "metadata": {"run_id": run_id}}


def _run_graph(state: State, run_id: str, graph_input: dict | Command) -> None:
    """Executor task: run the graph until it pauses or ends. Never raises: an exception
    left in a Future nobody reads would vanish without a trace."""
    try:
        state.graph.invoke(graph_input, _config(run_id))
    except Exception as e:   # any failure must reach the runs row, or the run looks stuck
        logger.exception("Run %s failed", run_id)
        try:
            runs.set_error(state.pool, run_id, f"{type(e).__name__}: {e}")
        except Exception:
            logger.exception("Run %s: could not record the failure", run_id)
    finally:
        state.active.release(run_id)


@app.post("/runs", response_model=RunResponse, status_code=201)
def create_run(body: CreateRunRequest, request: Request):
    state = request.app.state
    row = runs.insert_run(state.pool, body.topic, body.guidance)
    state.active.claim(row["run_id"])   # a brand-new ID, so this always succeeds
    graph_input = {"topic": body.topic, "topic_source": "user", "guidance": body.guidance}
    state.executor.submit(_run_graph, state, row["run_id"], graph_input)
    return RunResponse(**row, status=RunStatus.RUNNING)


@app.post("/runs/{run_id}/resume", response_model=RunResponse, status_code=202)
def resume_run(run_id: UUID, body: ResumeRequest, request: Request):
    """Send the human's decision to a run paused at approval."""
    state = request.app.state
    row = runs.get_run(state.pool, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    rid = row["run_id"]

    # Claim first, then check: a second request for the same run stops here
    if not state.active.claim(rid):
        raise HTTPException(status_code=409, detail="Run is busy")
    submitted = False
    try:
        snapshot = state.graph.get_state(_config(rid))
        status = derive_status(row, snapshot, active=False)   # our own claim doesn't count
        if status != RunStatus.AWAITING_APPROVAL:
            raise HTTPException(status_code=409, detail=f"Run is {status.value}, not awaiting approval")
        state.executor.submit(_run_graph, state, rid, Command(resume=body.model_dump()))
        submitted = True
    finally:
        if not submitted:
            state.active.release(rid)   # the runner releases it otherwise
    return to_response(row, snapshot, active=True)


@app.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: UUID, request: Request):
    state = request.app.state
    row = runs.get_run(state.pool, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    snapshot = state.graph.get_state(_config(row["run_id"]))
    return to_response(row, snapshot, active=row["run_id"] in state.active)


@app.get("/posts", response_model=list[PostOut])
def list_posts(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Published posts, newest first (the archive page)."""
    return posts.list_posts(request.app.state.pool, limit, offset)


@app.get("/posts/{run_id}", response_model=PostOut)
def get_post(run_id: UUID, request: Request):
    """The post a run published. 404 if the run is unknown or did not publish."""
    post = posts.get_post(request.app.state.pool, str(run_id))   # posts.run_id is text
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.get("/health")
def health():
    return {"status": "ok"}