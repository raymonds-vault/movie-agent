"""
Custom LangGraph agent factory.
Manages context optimization, history summarization, and agent self-reflection.
"""

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.agent.state import AgentState
from app.services.agent.prompts import (
    MOVIE_AGENT_SYSTEM_PROMPT,
    SUMMARIZE_HISTORY_PROMPT,
    OPTIMIZE_CONTEXT_PROMPT,
    EVALUATE_QUALITY_PROMPT
)
from app.services.agent.tools import ALL_TOOLS

logger = get_logger(__name__)


def create_llm(settings: Settings) -> ChatOllama:
    """Create the Ollama LLM instance."""
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
    )


async def summarize_node(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings)
    
    history = state.get("raw_history", [])
    if not history:
        return {"history_summary": "No previous conversation."}
        
    # Build text log for efficient LLM reading
    chat_log = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in history])
    prompt = SUMMARIZE_HISTORY_PROMPT.format(chat_history=chat_log)
    
    res = await llm.ainvoke(prompt)
    return {"history_summary": res.content}


async def optimize_node(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings)
    
    prompt = OPTIMIZE_CONTEXT_PROMPT.format(
        user_query=state.get("user_query", ""),
        history_summary=state.get("history_summary", "None"),
        feedback_context=state.get("feedback_context", "None")
    )
    
    res = await llm.ainvoke(prompt)
    return {"optimized_query": res.content}


async def agent_node(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings).bind_tools(ALL_TOOLS)
    
    # 1. Base persona
    msgs: list[BaseMessage] = [SystemMessage(content=MOVIE_AGENT_SYSTEM_PROMPT)]
    
    # 2. Optimized instruction integrating context
    msgs.append(HumanMessage(content=state.get("optimized_query", "")))
    
    # 3. Native tool/AI execution loop tracking
    msgs.extend(state.get("messages", []))
    
    res = await llm.ainvoke(msgs)
    return {"messages": [res]}


async def evaluate_node(state: AgentState, config: RunnableConfig):
    settings = config.get("configurable", {}).get("settings")
    llm = create_llm(settings)
    
    messages = state.get("messages", [])
    if not messages:
        return {"quality_score": 10}
        
    last_message = messages[-1]
    
    prompt = EVALUATE_QUALITY_PROMPT.format(
        draft_response=last_message.content,
        user_query=state.get("user_query", "")
    )
    
    res = await llm.ainvoke(prompt)
    content = str(res.content).strip()
    
    score = 10
    try:
        first_line = content.split('\n')[0]
        parsed_digits = ''.join(filter(str.isdigit, first_line))
        if parsed_digits:
            score = int(parsed_digits)
    except Exception as e:
        logger.warning(f"Failed to parse quality score: {e}")
        
    # If the LLM generates a poor response, explicitly push a failing flag backward into the state context
    if score < 6:
        reason = content.split('\n')[-1]
        msg = HumanMessage(content=f"Quality Evaluation Failed (Score: {score}/10). Reason: {reason}. Please rethink your answer completely and provide a better response.")
        return {"quality_score": score, "messages": [msg]}
        
    return {"quality_score": score}


def agent_router(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "evaluate"
        
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "evaluate"


def evaluate_router(state: AgentState) -> str:
    # Recursively return to agent if evaluated poorly
    if state.get("quality_score", 10) < 6:
        return "agent"
    return END


def create_movie_agent(settings: Settings):
    """
    Constructs the stateful LangGraph engine with discrete analytical nodes.
    """
    graph = StateGraph(AgentState)
    
    # Register Nodes
    graph.add_node("summarize", summarize_node)
    graph.add_node("optimize", optimize_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_node("evaluate", evaluate_node)
    
    # Define Edges
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", "optimize")
    graph.add_edge("optimize", "agent")
    
    # Native Conditional Routing
    graph.add_conditional_edges("agent", agent_router, {"tools": "tools", "evaluate": "evaluate"})
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("evaluate", evaluate_router, {"agent": "agent", END: END})
    
    logger.info("Custom Movie Agent LangGraph fully compiled!")
    
    # Compile graph securely, passing settings as valid config
    return graph.compile()
