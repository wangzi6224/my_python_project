from __future__ import annotations

from uuid import uuid4

from src.app.services.multi_agent.schemas import (
    AgentArtifact,
    AgentRole,
    HandoffMessage,
)


class HandoffBuilder:
    def build(
        self,
        *,
        from_role: AgentRole,
        to_role: AgentRole,
        artifact: AgentArtifact,
        task_id: str | None = None,
        constraints: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> HandoffMessage:
        return HandoffMessage(
            id=f"handoff_{uuid4().hex}",
            from_role=from_role,
            to_role=to_role,
            task_id=task_id,
            summary=artifact.content[:1000],
            artifact_ids=[artifact.id],
            constraints=constraints or [],
            open_questions=open_questions or [],
            confidence=artifact.confidence,
            payload={
                "artifact_type": artifact.artifact_type,
                "artifact_title": artifact.title,
                "source_count": len(artifact.source_refs),
            },
        )
