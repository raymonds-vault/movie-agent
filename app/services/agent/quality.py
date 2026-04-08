"""Shared quality evaluation for cache hits, graph answers, and regenerate flow."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.agent.llm_factory import create_llm_for_step
from app.services.agent.prompts import QUALITY_EVAL_SYSTEM_PROMPT

logger = get_logger(__name__)


def should_run_llm_quality_eval(
    settings: Settings,
    *,
    user_query: str,
    draft_response: str,
    tool_calls_made: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Fast rule gate:
    - skip expensive quality eval on obviously adequate answers
    - trigger eval when confidence is low
    """
    text = (draft_response or "").strip()
    if not text:
        return True, "empty_response"
    if len(text) < settings.QUALITY_RULE_MIN_CHARS:
        return True, "too_short"
    q = (user_query or "").lower()
    needs_tools = any(k in q for k in ["recommend", "movie", "details", "imdb", "search"])
    if needs_tools and not (tool_calls_made or []):
        return True, "missing_tool_evidence"
    return False, "rule_pass"


async def evaluate_answer_quality(
    settings: Settings,
    *,
    user_query: str,
    draft_response: str,
    source: str,
    run_config: dict | None = None,
) -> tuple[int, str]:
    """
    Score 1–10 and short reason. ``source`` is ``cache`` | ``graph`` | ``regenerate`` for logging.
    """
    if not (draft_response or "").strip():
        return 1, "Empty response"

    llm = create_llm_for_step(settings, "quality")
    human = HumanMessage(
        content=(
            f"User request:\n{user_query}\n\n"
            f"Assistant draft to evaluate:\n{draft_response}\n\n"
            "Reply on line 1 with only an integer 1–10. Line 2: one short sentence."
        )
    )
    cfg = run_config or {}
    res = await llm.ainvoke(
        [SystemMessage(content=QUALITY_EVAL_SYSTEM_PROMPT), human],
        config=cfg,
    )
    text = str(res.content or "").strip()
    score = 5
    reason = text
    try:
        first = text.split("\n")[0]
        digits = "".join(c for c in first if c.isdigit())
        if digits:
            score = max(1, min(10, int(digits[:2]) if len(digits) > 1 and int(digits[:2]) <= 10 else int(digits[0])))
        lines = [ln for ln in text.split("\n") if ln.strip()]
        if len(lines) > 1:
            reason = lines[1].strip()
        elif len(lines) == 1 and digits:
            reason = first
    except Exception as e:
        logger.warning("Quality parse failed (%s): %s", source, e)

    logger.debug("Quality [%s] score=%s", source, score)
    return score, reason
