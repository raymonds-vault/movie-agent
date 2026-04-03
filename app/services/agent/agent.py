"""
LangGraph: summarize → optimize prompt → tools ⇄ tool node → synthesize → quality → (retry synth or end).

Semantic cache + quality gate live in ChatService before the graph.
"""

from __future__ import annotations

from langchain_ollama import ChatOllama
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables.config import RunnableConfig
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
from app.services.agent.quality import evaluate_answer_quality
from app.services.agent.state import AgentState
from app.services.agent.tools import ALL_TOOLS

logger = get_logger(__name__)

MAX_TOOL_PHASE_ROUNDS = 8


def create_llm(settings: Settings) -> ChatOllama:
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
    )


def create_llm_synth(settings: Settings, *, use_fallback: bool) -> ChatOllama:
    if use_fallback:
        name = (
            (settings.OLLAMA_SYNTH_FALLBACK_MODEL or "").strip()
            or settings.OLLAMA_CODE_MODEL
            or settings.OLLAMA_MODEL
        )
        return ChatOllama(
            model=name,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.15,
        )
    return create_llm(settings)


async def summarize_history(state: AgentState, config: RunnableConfig):
    """Rolling summary — compact memory instead of long raw history in later nodes."""
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings)
    raw = state.get("raw_history") or []
    if not raw:
        return {"history_summary": "No prior conversation."}
    chat_turns = "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}" for m in raw
    )
    prompt = SUMMARY_HISTORY_PROMPT.format(chat_turns=chat_turns)
    res = await llm.ainvoke(prompt, config=config)
    return {"history_summary": (res.content or "").strip() or "No prior conversation."}


async def optimize_prompt(state: AgentState, config: RunnableConfig):
    """Short instruction for tool phase — reduces tokens / latency before tools + LLM."""
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings)
    prompt = OPTIMIZE_PRE_LLM_PROMPT.format(
        history_summary=state.get("history_summary", "None"),
        user_query=state.get("user_query", ""),
        feedback_context=state.get("feedback_context", "None"),
    )
    res = await llm.ainvoke(prompt, config=config)
    return {"optimized_prompt": (res.content or "").strip() or state.get("user_query", "")}


def _tools_phase_human_block(state: AgentState) -> str:
    return (
        f"Conversation summary (memory):\n{state.get('history_summary', 'None')}\n\n"
        f"Optimized task:\n{state.get('optimized_prompt', state.get('user_query', ''))}\n\n"
        f"Latest user message:\n{state.get('user_query', '')}"
    )


def _research_transcript(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            continue
        if isinstance(m, HumanMessage):
            lines.append(f"Human:\n{m.content}")
        elif isinstance(m, AIMessage):
            chunk = f"Assistant:\n{m.content or ''}"
            if m.tool_calls:
                chunk += f"\n[tool_calls: {len(m.tool_calls)}]"
            lines.append(chunk)
        elif isinstance(m, ToolMessage):
            lines.append(f"Tool ({m.name}):\n{m.content}")
        else:
            lines.append(f"{type(m).__name__}:\n{getattr(m, 'content', '')}")
    return "\n\n---\n\n".join(lines) if lines else "(no research)"


async def tools_phase(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings).bind_tools(ALL_TOOLS)

    prev = state.get("tool_rounds", 0)
    next_round = prev + 1

    if next_round > MAX_TOOL_PHASE_ROUNDS:
        logger.warning(
            "Tool phase round cap (%s) reached; forcing synthesizer.",
            MAX_TOOL_PHASE_ROUNDS,
        )
        return {
            "tool_rounds": prev,
            "messages": [
                AIMessage(
                    content="[Research stopped at cap]: use tool results above and conversation context."
                )
            ],
        }

    existing = list(state.get("messages") or [])
    if not existing:
        msgs: list[BaseMessage] = [
            SystemMessage(content=TOOLS_PHASE_SYSTEM_PROMPT),
            HumanMessage(content=_tools_phase_human_block(state)),
        ]
    else:
        msgs = existing

    res = await llm.ainvoke(msgs, config=config)
    return {"messages": [res], "tool_rounds": next_round}


async def synthesizer(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    prev = state.get("synthesis_pass_count", 0)
    use_fallback = prev >= 1
    llm = create_llm_synth(settings, use_fallback=use_fallback)
    research = list(state.get("messages") or [])
    transcript = _research_transcript(research)
    fb = (state.get("quality_feedback") or "").strip()
    retry_hint = ""
    if fb and prev >= 1:
        retry_hint = f"\n\nPrevious answer was weak. Improve using this feedback: {fb}"

    human = HumanMessage(
        content=(
            f"Answer the user's latest message using the research and summary below.{retry_hint}\n\n"
            f"--- Conversation summary ---\n{state.get('history_summary', '')}\n\n"
            f"--- Optimized task ---\n{state.get('optimized_prompt', '')}\n\n"
            f"--- User message ---\n{state.get('user_query', '')}\n\n"
            f"--- Tool research ---\n{transcript}"
        )
    )
    msgs = [SystemMessage(content=MOVIE_AGENT_SYSTEM_PROMPT), human]
    res = await llm.ainvoke(msgs, config=config)
    text = str(res.content or "").strip()
    return {"final_response": text, "synthesis_pass_count": prev + 1}


async def quality_eval(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    score, reason = await evaluate_answer_quality(
        settings,
        user_query=state.get("user_query", ""),
        draft_response=state.get("final_response") or "",
        source="graph",
        run_config=config,
    )
    return {"quality_score": score, "quality_feedback": reason}


def route_after_tools_phase(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return "synthesizer"
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "synthesizer"


def create_movie_agent(settings: Settings):
    min_q = settings.QUALITY_MIN_SCORE
    max_passes = settings.MAX_SYNTHESIS_PASSES

    def route_after_quality(state: AgentState) -> str:
        if state.get("quality_score", 0) >= min_q:
            return "end"
        if state.get("synthesis_pass_count", 0) >= max_passes:
            return "end"
        return "synthesizer"

    graph = StateGraph(AgentState)
    graph.add_node("summarize_history", summarize_history)
    graph.add_node("optimize_prompt", optimize_prompt)
    graph.add_node("tools_phase", tools_phase)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("quality_eval", quality_eval)

    graph.add_edge(START, "summarize_history")
    graph.add_edge("summarize_history", "optimize_prompt")
    graph.add_edge("optimize_prompt", "tools_phase")
    graph.add_conditional_edges(
        "tools_phase",
        route_after_tools_phase,
        {"tools": "tools", "synthesizer": "synthesizer"},
    )
    graph.add_edge("tools", "tools_phase")
    graph.add_edge("synthesizer", "quality_eval")
    graph.add_conditional_edges(
        "quality_eval",
        route_after_quality,
        {"end": END, "synthesizer": "synthesizer"},
    )

    logger.info(
        "Movie Agent LangGraph compiled (summary → optimize → tools → LLM → quality)."
    )
    return graph.compile()
