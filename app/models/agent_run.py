"""
Agent-run and analytics ORM models.

These tables persist graph-independent run intelligence:
- run input/output and lifecycle
- per-step transitions
- tool invocations
- quality gates
- cache decisions
- rolling conversation summaries
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(20), default="graph")  # graph|cache|regenerate
    path: Mapped[str] = mapped_column(String(20), default="sync")  # sync|stream
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    optimized_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    observability_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    steps: Mapped[list["AgentRunStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )
    quality_evaluations: Mapped[list["QualityEvaluation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class AgentRunStep(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_run_steps"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)  # chain_start/chain_end/llm...
    status: Mapped[str] = mapped_column(String(20), default="ok")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["AgentRun"] = relationship(back_populates="steps")


class ToolCall(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tool_calls"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_run_steps.id", ondelete="SET NULL"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(default=True)

    run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")


class QualityEvaluation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "quality_evaluations"

    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), default="graph")  # cache|graph|regenerate
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    run: Mapped["AgentRun"] = relationship(back_populates="quality_evaluations")


class CacheDecisionAudit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cache_decisions"

    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    user_scope: Mapped[str | None] = mapped_column(String(120), nullable=True)
    context_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(nullable=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)  # hit/rejected/miss/error
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ConversationSummary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    summary_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
