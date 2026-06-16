from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from src.app.services.multi_agent.schemas import (
    AgentArtifact,
    AgentRole,
    HandoffMessage,
    MultiAgentConfig,
    TaskPlan,
)


class MultiAgentState(BaseModel):
    run_id: str
    conversation_id: str
    user_message_id: str
    question: str
    rewritten_question: str | None = None
    model: str | None = None

    config: MultiAgentConfig = Field(default_factory=MultiAgentConfig)
    task_plan: TaskPlan | None = None

    artifacts: list[AgentArtifact] = Field(default_factory=list)
    handoffs: list[HandoffMessage] = Field(default_factory=list)
    roles_used: list[AgentRole] = Field(default_factory=list)
    role_runs: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    finish_reason: str | None = None
    review_decision: str | None = None

    trace_id: str | None = None
    assistant_run_id: str | None = None
    parent_span_id: str | None = None
    multi_agent_span_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_artifact(self, artifact: AgentArtifact) -> None:
        self.artifacts.append(artifact)
        if artifact.role not in self.roles_used:
            self.roles_used.append(artifact.role)

    def add_handoff(self, handoff: HandoffMessage) -> None:
        self.handoffs.append(handoff)
