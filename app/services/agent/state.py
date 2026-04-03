from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    Simplified graph:
    context_builder -> tools_decision (single pass) -> optional tool_executor -> synthesizer
    -> eval_gate -> optional quality_eval -> retry synth or end.
    """

    conversation_id: str
    user_query: str
    raw_history: list[dict[str, str]]
    feedback_context: str
    history_summary: str
    optimized_prompt: str
    messages: Annotated[list[BaseMessage], add_messages]
    synthesis_pass_count: int
    final_response: str
    quality_score: int
    quality_feedback: str
    quality_needs_eval: bool
