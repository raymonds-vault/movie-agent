"""
Normalize LangGraph astream_events (v2) into a compact timeline for the UI.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.config import Settings


def build_agent_run_config(
    settings: Settings,
    *,
    conversation_id: str,
    path: str,
    callbacks: list | None = None,
) -> RunnableConfig:
    """Tags, metadata, and optional Langfuse (or other) callbacks for graph runs."""
    cfg: dict[str, Any] = {
        "configurable": {"settings": settings},
        "tags": ["movie-agent", path],
        "metadata": {
            "conversation_id": conversation_id,
            "path": path,
            "langfuse_project": settings.LANGFUSE_PROJECT_NAME,
        },
    }
    if callbacks:
        cfg["callbacks"] = callbacks
    return cfg  # type: ignore[return-value]


def _truncate(s: str | None, max_len: int = 400) -> str | None:
    if s is None:
        return None
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def append_trace_from_astream_event(event: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    """Append one timeline row from a LangGraph ``astream_events`` v2 event."""
    kind = event.get("event") or ""
    name = (event.get("name") or "") or ""
    meta = event.get("metadata") or {}
    lg_node = meta.get("langgraph_node") or meta.get("langgraph_checkpoint_ns")
    data = event.get("data") or {}

    ts = time.time()
    row: dict[str, Any] = {"ts": ts, "event": kind, "name": name}

    if kind == "on_chain_start":
        label = lg_node or name
        if not label:
            return
        row["phase"] = "node_start"
        row["label"] = str(label)
        steps.append(row)
    elif kind == "on_chain_end":
        label = lg_node or name
        if not label:
            return
        row["phase"] = "node_end"
        row["label"] = str(label)
        steps.append(row)
    elif kind == "on_tool_start":
        row["phase"] = "tool_start"
        row["label"] = str(name or "tool")
        inp = data.get("input")
        if isinstance(inp, dict):
            row["detail"] = _truncate(str(inp.get("input") or inp))
        else:
            row["detail"] = _truncate(str(inp) if inp is not None else None)
        steps.append(row)
    elif kind == "on_tool_end":
        row["phase"] = "tool_end"
        row["label"] = str(name or "tool")
        out = data.get("output")
        row["detail"] = _truncate(str(out) if out is not None else None)
        steps.append(row)
    elif kind == "on_chat_model_start":
        row["phase"] = "llm_start"
        row["label"] = name or "chat_model"
        steps.append(row)


def try_get_observability_trace_id(handler: object | None) -> str | None:
    """Best-effort trace id from Langfuse ``CallbackHandler.last_trace_id`` after a run."""
    if handler is None:
        return None
    tid = getattr(handler, "last_trace_id", None)
    return str(tid) if tid else None
