from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from src.app.services.multi_agent.schemas import AgentRole


CoordinatorDecisionType = Literal[
    "run_role",
    "revise_role",
    "request_review",
    "skip_role",
    "final",
    "fail",
]


class CoordinatorDecision(BaseModel):
    """全局 Multi-Agent Coordinator 每一轮的结构化决策。"""

    type: CoordinatorDecisionType
    reason: str = Field(..., min_length=1, max_length=800)
    confidence: float = Field(default=0.7, ge=0, le=1)

    # run_role / revise_role / request_review 时使用
    role: AgentRole | None = None
    task_id: str | None = None
    task_title: str | None = None
    task_objective: str | None = None
    expected_output: str | None = None
    constraints: list[str] = Field(default_factory=list)
    input_artifact_ids: list[str] = Field(default_factory=list)
    input_handoff_ids: list[str] = Field(default_factory=list)

    # revise_role 时使用
    revision_of_artifact_id: str | None = None
    review_artifact_id: str | None = None
    review_feedback: dict[str, Any] | None = None

    # skip_role / fail / final 时使用
    target_role: AgentRole | None = None
    final_answer_instruction: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None


class CoordinatorRound(BaseModel):
    """一次全局 coordinator round。"""

    round_index: int
    decision: CoordinatorDecision
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"

    role_run_id: str | None = None
    artifact_id: str | None = None
    handoff_id: str | None = None

    latency_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CoordinatorGlobalState(BaseModel):
    """Level 3 全局动态状态。"""

    multi_agent_run_id: str
    conversation_id: str
    user_message_id: str
    question: str
    model: str | None = None

    max_rounds: int = 10
    max_role_steps: int = 10
    max_revisions: int = 1
    max_same_role_runs: int = 3
    max_failed_rounds: int = 2

    initial_constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    rounds: list[CoordinatorRound] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    role_runs: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    skipped_roles: list[AgentRole] = Field(default_factory=list)
    failed_round_count: int = 0
    revision_count: int = 0
    finish_reason: str | None = None

    trace_id: str | None = None
    assistant_run_id: str | None = None
    parent_span_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    def artifact_ids(self) -> set[str]:
        return {str(item.get("id")) for item in self.artifacts if item.get("id")}

    def role_run_count(self, role: AgentRole) -> int:
        return sum(1 for item in self.role_runs if item.get("role") == role)

    def latest_artifact_by_role(self, role: AgentRole) -> dict[str, Any] | None:
        for item in reversed(self.artifacts):
            if item.get("role") == role:
                return item
        return None
