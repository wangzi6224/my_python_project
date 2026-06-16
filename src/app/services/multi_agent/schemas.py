from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

# TaskPlan
# ├── SubTask(research)
# ├── SubTask(coding)
# └── SubTask(review)

# RoleRunResult(research)
# ├── artifact: AgentArtifact(research_report)
# └── handoff: HandoffMessage(research -> coding)

# RoleRunResult(coding)
# ├── artifact: AgentArtifact(coding_proposal)
# └── handoff: HandoffMessage(coding -> review)

# RoleRunResult(review)
# ├── artifact: AgentArtifact(review_report)
# └── data: ReviewArtifactData

# MultiAgentResult
# ├── answer
# ├── artifacts[]
# ├── handoffs[]
# ├── tool_calls[]
# └── trace

AgentRole = Literal[
    "supervisor",
    "research",
    "coding",
    "review",
    "final_synthesizer",
]

RoleRunStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
]

ArtifactType = Literal[
    "task_plan",
    "research_report",
    "coding_proposal",
    "review_report",
    "final_answer_context",
]

ReviewDecision = Literal[
    "pass",
    "needs_revision",
    "reject",
]


class MultiAgentConfig(BaseModel):
    """Multi-Agent 本轮执行配置。"""

    enabled: bool = False
    max_rounds: int = Field(default=10, ge=1, le=20)
    max_role_steps: int = Field(default=10, ge=1, le=30)
    enable_review: bool = True
    enable_mcp_tools: bool = True
    enable_graph_rag: bool = False
    model: str | None = None


class SubTask(BaseModel):
    """Supervisor 拆出来的子任务。"""

    id: str
    role: AgentRole
    title: str
    objective: str
    input_requirements: list[str] = Field(default_factory=list)
    expected_output: str
    depends_on: list[str] = Field(default_factory=list)
    priority: int = Field(default=50, ge=0, le=100)


class TaskPlan(BaseModel):
    """Supervisor 输出的任务计划。"""

    goal: str
    complexity: Literal["simple", "medium", "complex"] = "medium"
    should_use_multi_agent: bool = True
    reason: str
    subtasks: list[SubTask]
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)


class SourceRef(BaseModel):
    """资料来源引用。"""

    type: Literal["document", "chunk", "tool", "mcp", "memory", "unknown"] = "unknown"
    id: str | None = None
    title: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentArtifact(BaseModel):
    """角色输出的结构化产物。"""

    id: str
    role: AgentRole
    artifact_type: ArtifactType
    title: str
    content: str
    data: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HandoffMessage(BaseModel):
    """角色之间交接的信息。"""

    id: str
    from_role: AgentRole
    to_role: AgentRole
    task_id: str | None = None
    summary: str
    artifact_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class RoleRunResult(BaseModel):
    """单个角色执行结果。"""

    role: AgentRole
    status: RoleRunStatus
    artifact: AgentArtifact | None = None
    handoff: HandoffMessage | None = None
    latency_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    trace: dict[str, Any] = Field(default_factory=dict)


class ReviewArtifactData(BaseModel):
    """ReviewAgent 的结构化审查结果。"""

    decision: ReviewDecision
    issues: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    security_risks: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    score: float = Field(default=0.8, ge=0, le=1)


class MultiAgentResult(BaseModel):
    """MultiAgentService 对外返回结果。"""

    run_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str | None = None
    answer: str
    status: Literal["completed", "failed", "partial"]
    roles_used: list[AgentRole]
    artifacts: list[AgentArtifact]
    handoffs: list[HandoffMessage]
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
