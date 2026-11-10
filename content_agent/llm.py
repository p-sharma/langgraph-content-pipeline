import os
from functools import lru_cache
from langchain.chat_models import init_chat_model

@lru_cache(maxsize=1)
def get_llm():
    """Create the chant model once and reuse it everywhere."""
    model = os.getenv("LLM_MODEL","anthropic:claude-sonnet-5-5")
    return init_chat_model(model=model)


