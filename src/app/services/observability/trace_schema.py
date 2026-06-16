from __future__ import annotations

from enum import StrEnum
from typing import Any, Final, Literal
from pydantic import BaseModel, Field

SpanStatus = Literal["running", "success", "error", "cancelled"]


class SpanType(StrEnum):
    """统一 LLMOps span 类型，避免工程内散落字符串。"""

    # Assistant 主链路与路由 span。
    ASSISTANT_RUN = "assistant.run"
    ROUTER_DECISION = "router.decision"

    # 记忆相关 span，覆盖短期记忆加载、长期记忆检索和长期记忆写入。
    MEMORY_SHORT_TERM_LOAD = "memory.short_term.load"
    MEMORY_LONG_TERM_RETRIEVE = "memory.long_term.retrieve"
    MEMORY_LONG_TERM_WRITE = "memory.long_term.write"
    WORKING_MEMORY_UPDATE = "working_memory.update"

    # 上下文工程 span，覆盖普通组装、Agent 最终组装和上下文压缩。
    CONTEXT_ASSEMBLE = "context.assemble"
    CONTEXT_FINAL_ASSEMBLE = "context.final_assemble"
    CONTEXT_COMPRESS = "context.compress"

    # Agent 规划与工具调用 span。
    AGENT_RUN = "agent.run"
    QUERY_REWRITE = "query.rewrite"
    PLANNER_DECISION = "planner.decision"
    PLANNER_FALLBACK = "planner.fallback"
    TOOL_CALL = "tool.call"
    MCP_CALL = "mcp.call"

    # 模型、安全与评测 span。
    LLM_CALL = "llm.call"
    SECURITY_CHECK = "security.check"
    EVAL_JUDGE = "eval.judge"
    MULTI_AGENT_RUN = "multi_agent.run"
    MULTI_AGENT_SUPERVISOR = "multi_agent.supervisor"
    MULTI_AGENT_ROLE = "multi_agent.role"
    MULTI_AGENT_HANDOFF = "multi_agent.handoff"
    MULTI_AGENT_REVIEW = "multi_agent.review"


# 对外导出的常量别名，业务代码统一引用这些名称。
SPAN_TYPE_ASSISTANT_RUN: Final = SpanType.ASSISTANT_RUN
SPAN_TYPE_ROUTER_DECISION: Final = SpanType.ROUTER_DECISION
SPAN_TYPE_MEMORY_SHORT_TERM_LOAD: Final = SpanType.MEMORY_SHORT_TERM_LOAD
SPAN_TYPE_MEMORY_LONG_TERM_RETRIEVE: Final = SpanType.MEMORY_LONG_TERM_RETRIEVE
SPAN_TYPE_MEMORY_LONG_TERM_WRITE: Final = SpanType.MEMORY_LONG_TERM_WRITE
SPAN_TYPE_WORKING_MEMORY_UPDATE: Final = SpanType.WORKING_MEMORY_UPDATE
SPAN_TYPE_CONTEXT_ASSEMBLE: Final = SpanType.CONTEXT_ASSEMBLE
SPAN_TYPE_CONTEXT_FINAL_ASSEMBLE: Final = SpanType.CONTEXT_FINAL_ASSEMBLE
SPAN_TYPE_CONTEXT_COMPRESS: Final = SpanType.CONTEXT_COMPRESS
SPAN_TYPE_AGENT_RUN: Final = SpanType.AGENT_RUN
SPAN_TYPE_QUERY_REWRITE: Final = SpanType.QUERY_REWRITE
SPAN_TYPE_PLANNER_DECISION: Final = SpanType.PLANNER_DECISION
SPAN_TYPE_PLANNER_FALLBACK: Final = SpanType.PLANNER_FALLBACK
SPAN_TYPE_TOOL_CALL: Final = SpanType.TOOL_CALL
SPAN_TYPE_MCP_CALL: Final = SpanType.MCP_CALL
SPAN_TYPE_LLM_CALL: Final = SpanType.LLM_CALL
SPAN_TYPE_SECURITY_CHECK: Final = SpanType.SECURITY_CHECK
SPAN_TYPE_EVAL_JUDGE: Final = SpanType.EVAL_JUDGE
SPAN_TYPE_MULTI_AGENT_RUN: Final = SpanType.MULTI_AGENT_RUN
SPAN_TYPE_MULTI_AGENT_SUPERVISOR: Final = SpanType.MULTI_AGENT_SUPERVISOR
SPAN_TYPE_MULTI_AGENT_ROLE: Final = SpanType.MULTI_AGENT_ROLE
SPAN_TYPE_MULTI_AGENT_HANDOFF: Final = SpanType.MULTI_AGENT_HANDOFF
SPAN_TYPE_MULTI_AGENT_REVIEW: Final = SpanType.MULTI_AGENT_REVIEW

# 统一维护全部合法 span 类型，便于后续 schema、校验或 UI 复用。
SPAN_TYPES: Final = tuple(SpanType)


class TokenUsage(BaseModel):
    """一次模型调用的 token 使用情况。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CostUsage(BaseModel):
    """一次模型调用的成本估算。"""

    currency: str = "USD"
    prompt_cost: float = 0
    completion_cost: float = 0
    total_cost: float = 0
    estimated: bool = True


class TraceSpanCreate(BaseModel):
    """创建 span 的请求模型。"""

    trace_id: str
    parent_span_id: str | None = None
    run_id: str
    conversation_id: str | None = None
    assistant_run_id: str | None = None
    agent_run_id: str | None = None
    span_type: SpanType
    name: str
    input: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceSpan(BaseModel):
    """统一 LLMOps Span。"""

    id: str
    trace_id: str
    parent_span_id: str | None = None
    run_id: str
    conversation_id: str | None = None
    assistant_run_id: str | None = None
    agent_run_id: str | None = None
    span_type: SpanType
    name: str
    status: SpanStatus
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = None
    started_at: str | None = None
    ended_at: str | None = None


class TraceTree(BaseModel):
    """前端 Trace Drawer 使用的树结构。"""

    trace_id: str
    spans: list[TraceSpan]
    summary: dict[str, Any] = Field(default_factory=dict)
