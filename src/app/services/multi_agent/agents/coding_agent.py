from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.app.services.multi_agent.agents.base import BaseRoleAgent
from src.app.services.multi_agent.prompts import (
    CODING_PROMPT_VERSION,
    CODING_SYSTEM_PROMPT,
)
from src.app.services.multi_agent.schemas import AgentArtifact, RoleRunResult


class CodingAgent(BaseRoleAgent):
    role = "coding"
    prompt_version = CODING_PROMPT_VERSION

    def run(
        self,
        *,
        question: str,
        research_artifact: AgentArtifact,
        constraints: list[str],
        model: str | None = None,
        **_: Any,
    ) -> RoleRunResult:
        messages = [
            {"role": "system", "content": CODING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户问题：\n{question}\n\n"
                    f"ResearchArtifact：\n{research_artifact.content}\n\n"
                    f"必须遵守的约束：\n{constraints}\n\n"
                    "请输出工程设计、目录结构、关键代码片段和接入说明。"
                ),
            },
        ]

        response = self.llm_provider.chat(
            messages=messages,
            model=model,
            thinking_enabled=False,
        )

        artifact = AgentArtifact(
            id=f"artifact_{uuid4().hex}",
            role="coding",
            artifact_type="coding_proposal",
            title="CodingAgent 工程方案",
            content=response.content,
            data={
                "model": response.model,
                "provider": response.provider,
            },
            source_refs=research_artifact.source_refs,
            confidence=0.72,
            metadata={"prompt_version": self.prompt_version},
        )

        return RoleRunResult(
            role="coding",
            status="completed",
            artifact=artifact,
            trace={
                "prompt_version": self.prompt_version,
                "input_artifact_id": research_artifact.id,
                "answer_chars": len(response.content),
            },
        )
