"""Latency-optimized LangGraph: context_builder(optional) -> tools_decision(single pass) -> synthesizer -> conditional quality."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.agent.prompts import (
    MOVIE_AGENT_SYSTEM_PROMPT,
    OPTIMIZE_PRE_LLM_PROMPT,
    SUMMARY_HISTORY_PROMPT,
    TOOLS_PHASE_SYSTEM_PROMPT,
)
from app.services.agent.quality import evaluate_answer_quality, should_run_llm_quality_eval
from app.services.agent.state import AgentState
from app.services.agent.tools import ALL_TOOLS

logger = get_logger(__name__)


def _model_or(default: str, override: str | None) -> str:
    return (override or "").strip() or default


def create_llm_for_step(settings: Settings, step: str, *, use_fallback: bool = False) -> ChatOllama:
    if step == "context":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_CONTEXT_MODEL)
        temp = 0.0
    elif step == "tool_decision":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_TOOL_DECISION_MODEL)
        temp = 0.0
    elif step == "quality":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_QUALITY_MODEL)
        temp = 0.0
    else:  # synth
        if use_fallback:
            model = (
                (settings.OLLAMA_SYNTH_FALLBACK_MODEL or "").strip()
                or settings.OLLAMA_CODE_MODEL
                or settings.OLLAMA_MODEL
            )
            temp = 0.15
        else:
            model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_SYNTH_MODEL)
            temp = 0.0
    return ChatOllama(model=model, base_url=settings.OLLAMA_BASE_URL, temperature=temp)


def _research_transcript(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        # For final synthesis, only expose tool outputs (not internal chain chatter/tool-call metadata).
        if isinstance(m, ToolMessage):
            tool_name = m.name or "tool"
            tool_output = str(m.content or "").strip()
            lines.append(f"- {tool_name}: {tool_output}")
    return "\n".join(lines) if lines else "(no tool evidence)"


async def context_builder(state: AgentState, config: RunnableConfig):
    """Optional summary + prompt optimization in one node."""
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

    llm = create_llm_for_step(settings, "context")
    optimized = await llm.ainvoke(
        OPTIMIZE_PRE_LLM_PROMPT.format(
            history_summary=summary,
            user_query=state.get("user_query", ""),
            feedback_context=state.get("feedback_context", "None"),
        ),
        config=config,
    )
    return {
        "history_summary": summary,
        "optimized_prompt": (optimized.content or "").strip() or state.get("user_query", ""),
    }


def _tools_human_block(state: AgentState) -> str:
    return (
        f"Conversation summary:\n{state.get('history_summary', 'None')}\n\n"
        f"Optimized task:\n{state.get('optimized_prompt', state.get('user_query', ''))}\n\n"
        f"Latest user message:\n{state.get('user_query', '')}"
    )


async def tools_decision(state: AgentState, config: RunnableConfig):
    """Single LLM pass: decide zero/one tool calls (no recursive loop)."""
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
    llm = create_llm_for_step(settings, "synth", use_fallback=prev >= 1)
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
    return {"final_response": str(res.content or "").strip(), "synthesis_pass_count": prev + 1}


async def eval_gate(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    tools = [m.name for m in (state.get("messages") or []) if isinstance(m, ToolMessage)]
    needs_eval, reason = should_run_llm_quality_eval(
        settings,
        user_query=state.get("user_query", ""),
        draft_response=state.get("final_response") or "",
        tool_calls_made=tools,
    )
    if not needs_eval:
        return {"quality_score": 10, "quality_feedback": "rule_pass", "quality_needs_eval": False}
    return {"quality_score": 0, "quality_feedback": reason, "quality_needs_eval": True}


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
    return {"quality_score": score, "quality_feedback": reason}


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
    max_passes = settings.MAX_SYNTHESIS_PASSES

    def route_after_quality_eval(state: AgentState) -> str:
        if state.get("quality_score", 0) >= min_q:
            return "end"
        if state.get("synthesis_pass_count", 0) >= max_passes:
            return "end"
        return "synthesizer"

    graph = StateGraph(AgentState)
    graph.add_node("context_builder", context_builder)
    graph.add_node("tools_decision", tools_decision)
    graph.add_node("tool_executor", ToolNode(ALL_TOOLS))
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("eval_gate", eval_gate)
    graph.add_node("quality_eval", quality_eval)

    graph.add_edge(START, "context_builder")
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

    logger.info("Movie Agent LangGraph compiled (context_builder -> tools_decision -> synth -> conditional_eval).")
    return graph.compile()
