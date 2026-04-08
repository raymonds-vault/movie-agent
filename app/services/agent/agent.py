"""LangGraph: pinecone_context -> context_builder -> tools_decision -> synthesizer -> eval_gate -> quality_eval."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.agent.llm_factory import create_llm_for_step, create_llm_for_synth_tier
from app.services.agent.prompt_optimization import build_optimized_prompt
from app.services.agent.prompts import MOVIE_AGENT_SYSTEM_PROMPT, SUMMARY_HISTORY_PROMPT, TOOLS_PHASE_SYSTEM_PROMPT
from app.services.agent.quality import evaluate_answer_quality, should_run_llm_quality_eval
from app.services.agent.state import AgentState
from app.services.agent.tools import ALL_TOOLS
from app.services.pinecone_movie_rag import get_pinecone_movie_rag

logger = get_logger(__name__)


def _research_transcript(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        if isinstance(m, ToolMessage):
            tool_name = m.name or "tool"
            tool_output = str(m.content or "").strip()
            lines.append(f"- {tool_name}: {tool_output}")
    return "\n".join(lines) if lines else "(no tool evidence)"


async def pinecone_context(state: AgentState, config: RunnableConfig):
    """Retrieve movie context from Pinecone (skipped if not configured)."""
    settings = config.get("configurable", {}).get("settings")
    rag = get_pinecone_movie_rag(settings)
    uq = state.get("user_query", "")
    hist = (state.get("history_summary") or "").strip()
    raw = state.get("raw_history") or []
    recent_excerpt = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in raw[-4:]
    )
    history_hint = f"{hist}\n{recent_excerpt}".strip()

    if not rag.available:
        return {
            "retrieved_movie_context": "",
            "retrieval_score": None,
        }

    hits, best = await rag.query_movies(query_text=uq, history_hint=history_hint)
    ctx = rag.format_context(hits)
    return {
        "retrieved_movie_context": ctx,
        "retrieval_score": best,
    }


async def context_builder(state: AgentState, config: RunnableConfig):
    """History summary (optional LLM) + template/rule optimized task."""
    settings = config.get("configurable", {}).get("settings")
    existing_summary = (state.get("history_summary") or "").strip()
    raw = state.get("raw_history") or []
    needs_summary = (not existing_summary) and len(raw) >= settings.HISTORY_SUMMARY_MIN_MESSAGES

    summary = existing_summary or "No prior conversation."
    if needs_summary:
        llm = create_llm_for_step(settings, "context")
        chat_turns = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in raw
        )
        res = await llm.ainvoke(SUMMARY_HISTORY_PROMPT.format(chat_turns=chat_turns), config=config)
        summary = (res.content or "").strip() or summary

    optimized = build_optimized_prompt(
        user_query=state.get("user_query", ""),
        history_summary=summary,
        feedback_context=state.get("feedback_context", "None"),
        retrieved_movie_context=state.get("retrieved_movie_context", ""),
        raw_history=raw,
    )
    return {
        "history_summary": summary,
        "optimized_prompt": optimized,
    }


def _tools_human_block(state: AgentState) -> str:
    return (
        f"Conversation summary:\n{state.get('history_summary', 'None')}\n\n"
        f"Optimized task:\n{state.get('optimized_prompt', state.get('user_query', ''))}\n\n"
        f"Latest user message:\n{state.get('user_query', '')}"
    )


async def tools_decision(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm_for_step(settings, "tool_decision").bind_tools(ALL_TOOLS)
    msgs: list[BaseMessage] = [
        SystemMessage(content=TOOLS_PHASE_SYSTEM_PROMPT),
        HumanMessage(content=_tools_human_block(state)),
    ]
    res = await llm.ainvoke(msgs, config=config)
    return {"messages": [res]}


async def synthesizer(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    prev = state.get("synthesis_pass_count", 0)
    tier_idx = max(0, prev)
    llm = create_llm_for_synth_tier(settings, tier_idx)
    transcript = _research_transcript(list(state.get("messages") or []))
    retry_hint = ""
    if prev >= 1 and state.get("quality_feedback"):
        retry_hint = f"\n\nImprove this according to feedback: {state.get('quality_feedback')}"
    human = HumanMessage(
        content=(
            f"Answer using summary + tool evidence.{retry_hint}\n\n"
            "Important output constraints:\n"
            "- Return only the final user-facing answer.\n"
            "- Do NOT mention tool calls, internal chain steps, transcript labels, or debug notes.\n"
            "- Do NOT print strings like [tool_calls: ...], Tool(...), Assistant:, Human:, or 'let me try again'.\n"
            "- If earlier info was wrong, present a clean corrected answer directly.\n\n"
            f"--- Summary ---\n{state.get('history_summary', '')}\n\n"
            f"--- Task ---\n{state.get('optimized_prompt', '')}\n\n"
            f"--- User ---\n{state.get('user_query', '')}\n\n"
            f"--- Evidence ---\n{transcript}"
        )
    )
    res = await llm.ainvoke([SystemMessage(content=MOVIE_AGENT_SYSTEM_PROMPT), human], config=config)
    new_count = prev + 1
    return {
        "final_response": str(res.content or "").strip(),
        "synthesis_pass_count": new_count,
        "synthesis_model_tier": tier_idx,
        "retry_count": max(0, new_count - 1),
    }


async def eval_gate(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    tools = [m.name for m in (state.get("messages") or []) if isinstance(m, ToolMessage)]
    tool_used = ",".join(sorted(set(tools))) if tools else "none"
    needs_eval, reason = should_run_llm_quality_eval(
        settings,
        user_query=state.get("user_query", ""),
        draft_response=state.get("final_response") or "",
        tool_calls_made=tools,
    )
    if not needs_eval:
        return {
            "quality_score": 10,
            "quality_feedback": "rule_pass",
            "quality_needs_eval": False,
            "tool_used": tool_used,
            "eval_score": 10,
        }
    return {
        "quality_score": 0,
        "quality_feedback": reason,
        "quality_needs_eval": True,
        "tool_used": tool_used,
        "eval_score": None,
    }


async def quality_eval(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    if not state.get("quality_needs_eval", True):
        return {}
    score, reason = await evaluate_answer_quality(
        settings,
        user_query=state.get("user_query", ""),
        draft_response=state.get("final_response") or "",
        source="graph",
        run_config=config,
    )
    return {
        "quality_score": score,
        "quality_feedback": reason,
        "eval_score": score,
    }


def route_after_tools_decision(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return "synthesizer"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tool_executor"
    return "synthesizer"


def route_after_eval_gate(state: AgentState) -> str:
    return "quality_eval" if state.get("quality_needs_eval", False) else "end"


def create_movie_agent(settings: Settings):
    min_q = settings.QUALITY_MIN_SCORE
    good_enough = settings.QUALITY_GOOD_ENOUGH
    max_passes = settings.MAX_SYNTHESIS_PASSES

    def route_after_quality_eval(state: AgentState) -> str:
        score = int(state.get("quality_score") or 0)
        if score >= good_enough:
            return "end"
        if score >= min_q:
            return "end"
        if int(state.get("synthesis_pass_count", 0) or 0) >= max_passes:
            return "end"
        return "synthesizer"

    graph = StateGraph(AgentState)
    graph.add_node("pinecone_context", pinecone_context)
    graph.add_node("context_builder", context_builder)
    graph.add_node("tools_decision", tools_decision)
    graph.add_node("tool_executor", ToolNode(ALL_TOOLS))
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("eval_gate", eval_gate)
    graph.add_node("quality_eval", quality_eval)

    graph.add_edge(START, "pinecone_context")
    graph.add_edge("pinecone_context", "context_builder")
    graph.add_edge("context_builder", "tools_decision")
    graph.add_conditional_edges(
        "tools_decision",
        route_after_tools_decision,
        {"tool_executor": "tool_executor", "synthesizer": "synthesizer"},
    )
    graph.add_edge("tool_executor", "synthesizer")
    graph.add_edge("synthesizer", "eval_gate")
    graph.add_conditional_edges(
        "eval_gate",
        route_after_eval_gate,
        {"quality_eval": "quality_eval", "end": END},
    )
    graph.add_conditional_edges(
        "quality_eval",
        route_after_quality_eval,
        {"synthesizer": "synthesizer", "end": END},
    )

    logger.info(
        "Movie Agent LangGraph compiled (pinecone_context -> context_builder -> tools -> synth -> eval)."
    )
    return graph.compile()
