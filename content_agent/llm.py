import os
from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.runnables import Runnable
from pydantic import BaseModel

Role = Literal["searcher", "ranker", "researcher", "writer", "critic"]
DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"


@lru_cache(maxsize=None)
def get_llm(role: Role):
    """Create one chat model per role, the first time it's needed, and reuse it.

    The model comes from LLM_MODEL_<ROLE> (e.g. LLM_MODEL_WRITER), then LLM_MODEL,
    then DEFAULT_MODEL.
    """
    model = (
        os.getenv(f"LLM_MODEL_{role.upper()}")
        or os.getenv("LLM_MODEL")
        or DEFAULT_MODEL
    )
    return init_chat_model(model, max_tokens=4096)


def get_structured_llm(role: Role, schema: type[BaseModel]) -> Runnable:
    """A model for `role` whose output is parsed into `schema`.

    Uses the provider's native JSON-schema output (constrained decoding) instead of
    tool calling: newer Claude models can't be forced to call a tool, so tool-based
    structured output is unreliable on them.
    """
    return get_llm(role).with_structured_output(schema, method="json_schema")
