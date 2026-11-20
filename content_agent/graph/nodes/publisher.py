from langchain_core.runnables import RunnableConfig

from content_agent import posts
from content_agent.db import get_pool
from content_agent.graph.nodes.approval import critic_verdict
from content_agent.graph.state import State


def publisher(state: State, config: RunnableConfig) -> dict:
    """Graph node: store the approved draft as a post, then mark the run published.

    The run ID is the thread ID: LangGraph passes the run's config to any node that
    asks for a `config` parameter, so the run ID does not need its own State field.

    Errors are not caught. If the insert fails, the run stops here with its last
    checkpoint saying "publisher is next", so it can be retried; the API records
    the error and reports the run as failed. A retry that finds the post already
    stored is fine: insert_post leaves it unchanged.
    """
    run_id = config["configurable"]["thread_id"]
    post: posts.NewPost = {
        "run_id": run_id,
        "topic": state["topic"],
        "draft": state["draft"],
        "references": state.get("references", []),
        "critic_verdict": critic_verdict(state),        # the verdict the reviewer saw
        "edited": bool(state.get("human_feedback")),    # only request_changes sets it
    }
    stored = posts.insert_post(get_pool(), post)
    print(f"Publisher: {'stored post' if stored else 'post already stored, left unchanged'} ({run_id})")
    return {"status": "published"}
