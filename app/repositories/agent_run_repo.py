"""
Repositories for AgentRun persistence, cache audits, summaries, and analytics queries.
"""

from __future__ import annotations

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import (
    AgentRun,
    AgentRunStep,
    CacheDecisionAudit,
    ConversationSummary,
    QualityEvaluation,
    ToolCall,
)
from app.repositories.base import BaseRepository


class AgentRunRepository(BaseRepository[AgentRun]):
    def __init__(self, session: AsyncSession):
        super().__init__(AgentRun, session)

    async def create_run(
        self,
        *,
        conversation_id: str,
        user_query: str,
        source: str,
        path: str,
        parent_run_id: str | None = None,
        history_summary: str | None = None,
    ) -> AgentRun:
        return await self.create(
            conversation_id=conversation_id,
            parent_run_id=parent_run_id,
            user_query=user_query,
            source=source,
            path=path,
            history_summary=history_summary,
            status="running",
        )

    async def finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        final_response: str | None = None,
        quality_score: int | None = None,
        quality_feedback: str | None = None,
        optimized_prompt: str | None = None,
        history_summary: str | None = None,
        observability_trace_id: str | None = None,
    ) -> AgentRun | None:
        run = await self.get_by_id(run_id)
        if not run:
            return None
        run.status = status
        if final_response is not None:
            run.final_response = final_response
        if quality_score is not None:
            run.quality_score = quality_score
        if quality_feedback is not None:
            run.quality_feedback = quality_feedback
        if optimized_prompt is not None:
            run.optimized_prompt = optimized_prompt
        if history_summary is not None:
            run.history_summary = history_summary
        if observability_trace_id is not None:
            run.observability_trace_id = observability_trace_id
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def get_latest_by_conversation(self, conversation_id: str) -> AgentRun | None:
        stmt = (
            select(AgentRun)
            .where(AgentRun.conversation_id == conversation_id)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_step(
        self,
        *,
        run_id: str,
        node_name: str,
        event: str,
        status: str = "ok",
        detail: str | None = None,
    ) -> AgentRunStep:
        step = AgentRunStep(
            run_id=run_id,
            node_name=node_name,
            event=event,
            status=status,
            detail=detail,
        )
        self._session.add(step)
        await self._session.flush()
        return step

    async def add_tool_call(
        self,
        *,
        run_id: str,
        tool_name: str,
        tool_input: str | None = None,
        tool_output: str | None = None,
        latency_ms: int | None = None,
        success: bool = True,
    ) -> ToolCall:
        row = ToolCall(
            run_id=run_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            latency_ms=latency_ms,
            success=success,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def add_quality_evaluation(
        self,
        *,
        run_id: str,
        source: str,
        score: int,
        reason: str | None,
        model_name: str | None = None,
    ) -> QualityEvaluation:
        row = QualityEvaluation(
            run_id=run_id,
            source=source,
            score=score,
            reason=reason,
            model_name=model_name,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_tool_usage_stats(
        self, tool_name: str | None = None, limit: int = 50
    ) -> list[dict]:
        stmt = (
            select(
                ToolCall.tool_name,
                func.count(ToolCall.id).label("calls"),
                func.avg(ToolCall.latency_ms).label("avg_latency_ms"),
                func.sum(case((ToolCall.success == True, 1), else_=0)).label("success_count"),  # noqa: E712
            )
            .group_by(ToolCall.tool_name)
            .order_by(desc("calls"))
            .limit(limit)
        )
        if tool_name:
            stmt = stmt.where(ToolCall.tool_name == tool_name)
        result = await self._session.execute(stmt)
        rows = []
        for r in result.all():
            rows.append(
                {
                    "tool_name": r.tool_name,
                    "calls": int(r.calls or 0),
                    "avg_latency_ms": float(r.avg_latency_ms or 0),
                    "success_count": int(r.success_count or 0),
                }
            )
        return rows

    async def get_run_failure_breakdown(self, limit: int = 200) -> list[dict]:
        stmt = (
            select(AgentRunStep.node_name, AgentRunStep.status, func.count(AgentRunStep.id))
            .group_by(AgentRunStep.node_name, AgentRunStep.status)
            .order_by(desc(func.count(AgentRunStep.id)))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            {"node_name": n, "status": s, "count": int(c)}
            for n, s, c in result.all()
        ]


class CacheAuditRepository(BaseRepository[CacheDecisionAudit]):
    def __init__(self, session: AsyncSession):
        super().__init__(CacheDecisionAudit, session)

    async def log_decision(
        self,
        *,
        query: str,
        decision: str,
        reason: str | None = None,
        similarity_score: float | None = None,
        conversation_id: str | None = None,
        user_scope: str | None = None,
        context_hash: str | None = None,
        cache_key: str | None = None,
    ) -> CacheDecisionAudit:
        return await self.create(
            query=query,
            decision=decision,
            reason=reason,
            similarity_score=similarity_score,
            conversation_id=conversation_id,
            user_scope=user_scope,
            context_hash=context_hash,
            cache_key=cache_key,
        )

    async def decision_stats(self) -> list[dict]:
        stmt = (
            select(CacheDecisionAudit.decision, func.count(CacheDecisionAudit.id))
            .group_by(CacheDecisionAudit.decision)
            .order_by(desc(func.count(CacheDecisionAudit.id)))
        )
        result = await self._session.execute(stmt)
        return [{"decision": d, "count": int(c)} for d, c in result.all()]


class ConversationSummaryRepository(BaseRepository[ConversationSummary]):
    def __init__(self, session: AsyncSession):
        super().__init__(ConversationSummary, session)

    async def get_latest(self, conversation_id: str) -> ConversationSummary | None:
        stmt = (
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(ConversationSummary.summary_version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_next(
        self,
        *,
        conversation_id: str,
        summary_text: str,
        token_count: int | None = None,
    ) -> ConversationSummary:
        latest = await self.get_latest(conversation_id)
        next_version = 1 if latest is None else latest.summary_version + 1
        return await self.create(
            conversation_id=conversation_id,
            summary_text=summary_text,
            summary_version=next_version,
            token_count=token_count,
        )
