from __future__ import annotations

from src.app.services.multi_agent.schemas import AgentArtifact, HandoffMessage


class MultiAgentArtifactFormatter:
    def format_artifact(self, artifact: AgentArtifact) -> str:
        source_lines = []
        for source in artifact.source_refs[:10]:
            source_lines.append(
                f"- [{source.type}] {source.title or source.id or 'unknown'} score={source.score}"
            )

        return "\n".join(
            [
                "【Multi-Agent Artifact】",
                f"角色：{artifact.role}",
                f"类型：{artifact.artifact_type}",
                f"标题：{artifact.title}",
                f"置信度：{artifact.confidence}",
                "内容：",
                artifact.content,
                "来源：",
                "\n".join(source_lines) if source_lines else "无显式来源",
            ]
        )

    def format_handoff(self, handoff: HandoffMessage) -> str:
        return "\n".join(
            [
                "【Multi-Agent Handoff】",
                f"from：{handoff.from_role}",
                f"to：{handoff.to_role}",
                f"task_id：{handoff.task_id}",
                f"confidence：{handoff.confidence}",
                "summary：",
                handoff.summary,
                "constraints：",
                "\n".join(f"- {item}" for item in handoff.constraints) or "无",
                "open_questions：",
                "\n".join(f"- {item}" for item in handoff.open_questions) or "无",
            ]
        )
