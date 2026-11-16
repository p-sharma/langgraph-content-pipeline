from langgraph.graph import END, START, StateGraph

from content_agent.graph.nodes.ranker import ranker
from content_agent.graph.nodes.researcher import fan_out_to_researchers, research_source
from content_agent.graph.nodes.searcher import searcher
from content_agent.graph.state import State


def build_graph(checkpointer=None):
    """Wire all nodes and edges together and return a compiled graph."""
    builder = StateGraph(State)

    # Add Nodes
    builder.add_node("searcher", searcher)
    builder.add_node("ranker", ranker)
    builder.add_node("research_source", research_source)

    # --- Edges ---
    builder.add_edge(START, "searcher")
    builder.add_edge("searcher", "ranker")
    builder.add_conditional_edges("ranker", fan_out_to_researchers, ["research_source", END])
    builder.add_edge("research_source", END)   # → "writer" in the next step

    return builder.compile(checkpointer=checkpointer)