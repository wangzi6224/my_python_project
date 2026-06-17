from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from src.app.services.multi_agent.schemas import AgentRole


RoleDecisionType = Literal["tool_call", "final"]


class RolePlannerDecision(BaseModel):
    type: RoleDecisionType
    reason: str = Field(..., min_length=1, max_length=500)
    confidence: float = Field(default=0.7, ge=0, le=1)

    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

    artifact_title: str | None = None
    artifact_content: str | None = None
    artifact_data: dict[str, Any] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)


class RoleStep(BaseModel):
    step: int
    type: Literal["tool_call", "final", "error"]
    reason: str | None = None

    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None

    success: bool = True
    latency_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    decision: dict[str, Any] = Field(default_factory=dict)


class RoleObservation(BaseModel):
    step: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class AutonomousRoleState(BaseModel):
    multi_agent_run_id: str
    coordinator_round_index: int
    role_run_id: str | None = None
    role: AgentRole

    conversation_id: str
    user_message_id: str
    question: str
    model: str | None = None

    task_id: str | None = None
    task_title: str | None = None
    task_objective: str
    expected_output: str | None = None
    constraints: list[str] = Field(default_factory=list)

    input_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    input_handoffs: list[dict[str, Any]] = Field(default_factory=list)
    review_feedback: dict[str, Any] | None = None

    max_steps: int = 15
    steps: list[RoleStep] = Field(default_factory=list)
    observations: list[RoleObservation] = Field(default_factory=list)

    planner_decision_count: int = 0
    planner_fallback_count: int = 0
    finish_reason: str | None = None

    trace_id: str | None = None
    assistant_run_id: str | None = None
    parent_span_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
