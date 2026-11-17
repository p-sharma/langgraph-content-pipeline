import os
from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model

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
