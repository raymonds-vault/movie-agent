"""
LLM verification that a semantic-cache entry is an appropriate answer for the user query.
"""

from langchain_ollama import ChatOllama

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

VERIFY_PROMPT = """You are a strict judge. A USER QUERY was matched to a CACHED ANSWER using embedding similarity only. That match can be wrong.

Decide: Is the CACHED ANSWER an appropriate, correct, and complete-enough response to the USER QUERY for a movie assistant? It must address what the user actually asked, not merely be loosely related.

Reply with exactly ONE word on the first line: YES or NO. No punctuation, no explanation.

USER QUERY:
{user_query}

CACHED ANSWER:
{cached_answer}
"""


async def verify_semantic_cache_answer(
    settings: Settings,
    user_query: str,
    cached_answer: str,
) -> bool:
    """Return True only if the verifier LLM answers YES."""
    if not cached_answer or not cached_answer.strip():
        return False

    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0.0,
    )
    prompt = VERIFY_PROMPT.format(
        user_query=user_query.strip(),
        cached_answer=cached_answer.strip(),
    )
    try:
        res = await llm.ainvoke(prompt)
        raw = str(res.content).strip()
        first_line = raw.splitlines()[0].strip().upper()
        first_token = first_line.split()[0] if first_line.split() else ""
        if first_token.startswith("YES"):
            return True
        if first_token.startswith("NO"):
            return False
        # Conservative fallback if model is chatty
        if first_line.startswith("YES"):
            return True
        logger.warning(
            "Cache verifier unclear response %r; treating as NO",
            raw[:200],
        )
        return False
    except Exception as e:
        logger.error("Cache verification LLM failed: %s", e, exc_info=True)
        return False
