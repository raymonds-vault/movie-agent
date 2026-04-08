"""Structured agent checkpoints and escalation metrics."""

from __future__ import annotations

import threading
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_total_graph_runs = 0
_escalated_runs = 0


def record_graph_completion(*, escalated: bool) -> None:
    """escalated = retry_count > 0 or synthesis_model_tier > 0 at end."""
    global _total_graph_runs, _escalated_runs
    with _lock:
        _total_graph_runs += 1
        if escalated:
            _escalated_runs += 1


def escalation_rate() -> tuple[int, int, float]:
    """Returns (total, escalated, rate 0..1)."""
    with _lock:
        if _total_graph_runs == 0:
            return 0, 0, 0.0
        rate = _escalated_runs / _total_graph_runs
        return _total_graph_runs, _escalated_runs, rate


def log_agent_checkpoint(
    *,
    conversation_id: str | None,
    run_id: str | None,
    retrieval_score: float | None,
    tool_used: str | None,
    eval_score: int | None,
    retry_count: int | None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "checkpoint": "agent_turn",
        "conversation_id": conversation_id,
        "run_id": run_id,
        "retrieval_score": retrieval_score,
        "tool_used": tool_used,
        "eval_score": eval_score,
        "retry_count": retry_count,
        **(extra or {}),
    }
    t, e, r = escalation_rate()
    payload["escalation_rate_rolling"] = round(r, 4)
    payload["escalation_stats"] = {"total_runs": t, "escalated_runs": e}
    logger.info("agent_observability %s", payload)
