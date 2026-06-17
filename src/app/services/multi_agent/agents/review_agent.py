from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.app.services.multi_agent.prompts import (
    REVIEW_PROMPT_VERSION,
    REVIEW_SYSTEM_PROMPT,
)
from src.app.services.multi_agent.schemas import (
    AgentArtifact,
    ReviewArtifactData,
    RoleRunResult,
)
from src.app.services.multi_agent.agents.autonomous_role_agent import AutonomousRoleAgent



class ReviewAgent(AutonomousRoleAgent):
    role = "review"
    prompt_version = REVIEW_PROMPT_VERSION
    artifact_type = "review_report"
    default_artifact_title = "ReviewAgent 审查报告"

    def run(
        self,
        *,
        question: str,
        research_artifact: AgentArtifact,
        coding_artifact: AgentArtifact,
        constraints: list[str],
        model: str | None = None,
        **_: Any,
    ) -> RoleRunResult:
        try:
            response = self.llm_provider.structured_chat(
                messages=[
                    {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"用户问题：\n{question}\n\n"
                            f"ResearchArtifact：\n{research_artifact.content}\n\n"
                            f"CodingArtifact：\n{coding_artifact.content}\n\n"
                            f"必须遵守的约束：\n{constraints}"
                        ),
                    },
                ],
                model=model,
            )

            raw_content = response.content

            review = ReviewArtifactData.model_validate_json(raw_content)

        except Exception:
            review = self._fallback_review(coding_artifact=coding_artifact)

        content = "\n".join(
            [
                "ReviewAgent 审查报告",
                f"decision：{review.decision}",
                f"score：{review.score}",
                "",
                "问题：",
                "\n".join(f"- {item}" for item in review.issues) or "- 暂无",
                "",
                "缺失需求：",
                "\n".join(f"- {item}" for item in review.missing_requirements)
                or "- 暂无",
                "",
                "安全风险：",
                "\n".join(f"- {item}" for item in review.security_risks) or "- 暂无",
                "",
                "建议修复：",
                "\n".join(f"- {item}" for item in review.suggested_fixes) or "- 暂无",
            ]
        )

        artifact = AgentArtifact(
            id=f"artifact_{uuid4().hex}",
            role="review",
            artifact_type="review_report",
            title="ReviewAgent 审查报告",
            content=content,
            data=review.model_dump(mode="json"),
            source_refs=coding_artifact.source_refs,
            confidence=review.score,
            metadata={"prompt_version": self.prompt_version},
        )

        return RoleRunResult(
            role="review",
            status="completed",
            artifact=artifact,
            trace={
                "prompt_version": self.prompt_version,
                "decision": review.decision,
                "score": review.score,
            },
        )

    def _fallback_review(self, *, coding_artifact: AgentArtifact) -> ReviewArtifactData:
        content = coding_artifact.content
        issues: list[str] = []

        required_keywords = [
            "AssistantOrchestrator",
            "ContextAssembler",
            "Trace",
            "Eval",
            "ToolRegistry",
        ]
        for keyword in required_keywords:
            if keyword not in content:
                issues.append(f"方案中缺少关键模块说明：{keyword}")

        decision = "pass" if not issues else "needs_revision"
        return ReviewArtifactData(
            decision=decision,
            issues=issues,
            missing_requirements=issues,
            security_risks=[],
            suggested_fixes=["补齐缺失模块说明"] if issues else [],
            score=0.8 if not issues else 0.55,
        )
