from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict, total=False):
    """
    Standard state tracking for the Movie Agent.
    ``raw_history`` is recent DB turns (oldest-first) consumed by summarize_node.
    """

    conversation_id: str
    user_query: str
    raw_history: list[dict[str, str]]
    messages: Annotated[list[BaseMessage], add_messages]
    history_summary: str
    feedback_context: str
    optimized_query: str
    final_response: str
    quality_score: int
    quality_feedback: str
