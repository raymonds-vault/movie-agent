from app.core.config import Settings
from app.services.agent.agent import create_llm_for_step
from app.services.agent.quality import should_run_llm_quality_eval


def _settings() -> Settings:
    return Settings(
        APP_NAME="test",
        DATABASE_URL="mysql+aiomysql://root:Admin123@localhost:3306/movie_agent_test",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.1",
        OLLAMA_CODE_MODEL="deepseek-coder",
        OLLAMA_CONTEXT_MODEL="tiny-context",
        OLLAMA_TOOL_DECISION_MODEL="mid-tools",
        OLLAMA_SYNTH_MODEL="best-synth",
        OLLAMA_QUALITY_MODEL="tiny-judge",
        OLLAMA_SYNTH_FALLBACK_MODEL="fallback-synth",
        OMDB_API_KEY="k",
    )


def test_step_model_routing_prefers_step_override():
    s = _settings()
    assert create_llm_for_step(s, "context").model == "tiny-context"
    assert create_llm_for_step(s, "tool_decision").model == "mid-tools"
    assert create_llm_for_step(s, "synth").model == "best-synth"
    assert create_llm_for_step(s, "quality").model == "tiny-judge"


def test_synth_fallback_model_used_on_retry():
    s = _settings()
    assert create_llm_for_step(s, "synth", use_fallback=True).model == "fallback-synth"


def test_quality_rule_gate_skips_llm_when_confident():
    s = _settings()
    needs_eval, reason = should_run_llm_quality_eval(
        s,
        user_query="Recommend sci-fi movies",
        draft_response="Here are several strong sci-fi picks with short reasons and release years.",
        tool_calls_made=["search_movies"],
    )
    assert needs_eval is False
    assert reason == "rule_pass"


def test_quality_rule_gate_triggers_on_short_response():
    s = _settings()
    needs_eval, reason = should_run_llm_quality_eval(
        s,
        user_query="Recommend movies",
        draft_response="Try Inception.",
        tool_calls_made=["search_movies"],
    )
    assert needs_eval is True
    assert reason == "too_short"
