"""OpenAI-first chat models with Ollama fallback when API key is absent."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import Settings


def _model_or(default: str, override: str | None) -> str:
    return (override or "").strip() or default


def create_chat_model(
    settings: Settings,
    *,
    model_name: str,
    temperature: float = 0.0,
) -> BaseChatModel:
    if settings.openai_configured:
        return ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model=model_name,
            temperature=temperature,
        )
    return ChatOllama(
        model=model_name,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=temperature,
    )


def create_llm_for_step(settings: Settings, step: str, *, use_fallback: bool = False) -> BaseChatModel:
    """
    Maps logical steps to model names.
    - OpenAI: tiers / env overrides per step.
    - Fallback: Ollama with legacy OLLAMA_* routing.
    """
    tiers = settings.openai_chat_tiers
    tier0 = tiers[0] if tiers else "gpt-4o-mini"
    tier1 = tiers[1] if len(tiers) > 1 else tiers[0]

    if settings.openai_configured:
        if step == "context":
            model = (settings.OPENAI_CHAT_MODEL_CONTEXT or "").strip() or tier0
        elif step == "tool_decision":
            model = (settings.OPENAI_CHAT_MODEL_TOOLS or "").strip() or tier0
        elif step == "quality":
            model = (settings.OPENAI_CHAT_MODEL_QUALITY or "").strip() or tier0
        else:  # synth
            if use_fallback:
                model = tier1
            else:
                model = tier0
        return create_chat_model(settings, model_name=model, temperature=0.0 if step != "synth" else 0.0)

    # Ollama legacy
    if step == "context":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_CONTEXT_MODEL)
        temp = 0.0
    elif step == "tool_decision":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_TOOL_DECISION_MODEL)
        temp = 0.0
    elif step == "quality":
        model = _model_or(settings.OLLAMA_MODEL, settings.OLLAMA_QUALITY_MODEL)
        temp = 0.0
    else:
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


def create_llm_for_synth_tier(settings: Settings, tier_index: int) -> BaseChatModel:
    """tier_index 0 = cheapest; 1+ = more expensive."""
    tiers = settings.openai_chat_tiers
    if not tiers:
        tiers = ["gpt-4o-mini", "gpt-4o"]
    idx = max(0, min(tier_index, len(tiers) - 1))
    model_name = tiers[idx]
    temp = 0.15 if idx > 0 else 0.0
    if settings.openai_configured:
        return create_chat_model(settings, model_name=model_name, temperature=temp)
    # Ollama: first pass main model, else fallback
    use_fb = tier_index > 0
    return create_llm_for_step(settings, "synth", use_fallback=use_fb)


def get_llm_model_label(llm: BaseChatModel) -> str:
    m = getattr(llm, "model", None) or getattr(llm, "model_name", None)
    return str(m or "unknown")
