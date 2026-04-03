from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    **Cache** is applied in ChatService before the graph.

    Graph: ``summarize_history`` → ``optimize_prompt`` → ``tools_phase`` ⇄ ``tools``
    → ``synthesizer`` → ``quality_eval`` → (retry ``synthesizer`` or end).

    ``history_summary`` replaces long raw history in downstream prompts (latency).
    ``optimized_prompt`` is the compact instruction block for the tool phase.
    """

    conversation_id: str
    user_query: str
    raw_history: list[dict[str, str]]
    feedback_context: str
    history_summary: str
    optimized_prompt: str
    messages: Annotated[list[BaseMessage], add_messages]
    tool_rounds: int
    synthesis_pass_count: int
    final_response: str
    quality_score: int
    quality_feedback: str
