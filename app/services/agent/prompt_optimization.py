"""Template + rule-based task construction (no LLM optimization)."""

from __future__ import annotations

from app.services.agent.prompts import OPTIMIZED_TASK_TEMPLATE


def _recent_turns_excerpt(raw_history: list[dict[str, str]], max_turns: int = 4) -> str:
    if not raw_history:
        return ""
    tail = raw_history[-max_turns:]
    lines = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in tail]
    return "\n".join(lines)


def _follow_up_expansion(user_query: str, history_summary: str) -> str:
    q = (user_query or "").lower().strip()
    vague = ["more", "what else", "another", "that one", "which", "yes", "tell me more"]
    if any(v in q for v in vague) and (history_summary or "").strip():
        return f"(Follow-up in thread; context from summary: {history_summary[:400]})"
    return ""


def build_optimized_prompt(
    *,
    user_query: str,
    history_summary: str,
    feedback_context: str,
    retrieved_movie_context: str,
    raw_history: list[dict[str, str]],
) -> str:
    """Apply rules + template; cap total length."""
    summary = (history_summary or "").strip() or "No prior conversation."
    fb = (feedback_context or "").strip() or "None"
    retrieved = (retrieved_movie_context or "").strip()
    recent = _recent_turns_excerpt(raw_history or [])
    follow = _follow_up_expansion(user_query, summary)

    base = OPTIMIZED_TASK_TEMPLATE.format(
        history_summary=summary[:4000],
        user_query=(user_query or "").strip()[:4000],
        feedback_context=fb[:2000],
        retrieved_movie_context=retrieved[:6000] if retrieved else "(no retrieved movie context)",
        recent_turns=recent[:3000] if recent else "(no recent turns)",
    )
    if follow:
        base = f"{base}\n\nNote: {follow}"

    # Hard cap for routing
    if len(base) > 12000:
        base = base[:11999] + "…"
    return base.strip()
