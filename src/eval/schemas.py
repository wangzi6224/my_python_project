from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

EvalCategory = Literal[
    "route",
    "agent_tool",
    "memory",
    "context",
    "mcp_tool",
    "security",
    "regression",
    "multi_agent",
]


class EvalCase(BaseModel):
    """一条评测样本。

    设计原则：
    1. 不绑定某一个具体评测类型。
    2. expected 用 dict 保持扩展性。
    3. options 直接映射 AssistantOptions。
    """

    id: str
    category: EvalCategory
    message: str = Field(min_length=1)
    mode: Literal["auto", "chat", "agent", "mcp"] = "auto"
    expected: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EvalRunConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8000"
    conversation_id: str
    model: str | None = None
    provider: str | None = None
    timeout_seconds: int = 120
    fail_fast: bool = False
    baseline_path: str | None = None


class AssistantEvalOutput(BaseModel):
    """从 SSE 和 run detail 中收集到的统一输出。"""

    answer: str = ""
    assistant_run_id: str | None = None
    assistant_message_id: str | None = None
    agent_run_id: str | None = None

    route_decision: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] | None = None
    trace: dict[str, Any] | None = None
    trace_summary: dict[str, Any] | None = None
    multi_agent: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: int | None = None
    error: dict[str, Any] | None = None


class EvalCaseResult(BaseModel):
    case_id: str
    category: EvalCategory
    passed: bool
    score: float = Field(ge=0, le=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    output: AssistantEvalOutput
    expected: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EvalSuiteResult(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    category_summary: dict[str, dict[str, Any]]
    results: list[EvalCaseResult]
    regression: dict[str, Any] = Field(default_factory=dict)
