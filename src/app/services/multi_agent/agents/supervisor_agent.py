from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.app.services.multi_agent.agents.base import BaseRoleAgent
from src.app.services.multi_agent.prompts import (
    SUPERVISOR_PROMPT_VERSION,
    SUPERVISOR_SYSTEM_PROMPT,
)
from src.app.services.multi_agent.schemas import (
    AgentArtifact,
    RoleRunResult,
    SubTask,
    TaskPlan,
)


class SupervisorAgent(BaseRoleAgent):
    role = "supervisor"
    prompt_version = SUPERVISOR_PROMPT_VERSION

    def run(
        self,
        *,
        question: str,
        constraints: list[str],
        model: str | None = None,
        **_: Any,
    ) -> RoleRunResult:
        used_fallback = False
        llm_error: str | None = None
        raw_content: str | None = None

        try:
            response = self.llm_provider.structured_chat(
                messages=[
                    {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"用户问题：\n{question}\n\n"
                            f"必须遵守的约束：\n{constraints}"
                        ),
                    },
                ],
                model=model,
            )

            raw_content = response.content

            plan = TaskPlan.model_validate_json(raw_content)

        except Exception as exc:
            used_fallback = True
            llm_error = repr(exc)
            plan = self._fallback_plan(question=question, constraints=constraints)

        artifact = AgentArtifact(
            id=f"artifact_{uuid4().hex}",
            role="supervisor",
            artifact_type="task_plan",
            title="Multi-Agent 任务计划",
            content=plan.model_dump_json(indent=2),
            data=plan.model_dump(mode="json"),
            confidence=plan.confidence,
            metadata={
                "prompt_version": self.prompt_version,
                "used_fallback": used_fallback,
                "llm_error": llm_error,
            },
        )

        return RoleRunResult(
            role="supervisor",
            status="completed",
            artifact=artifact,
            trace={
                "task_plan": plan.model_dump(mode="json"),
                "prompt_version": self.prompt_version,
                "used_fallback": used_fallback,
                "llm_error": llm_error,
                "raw_content": raw_content,
            },
        )

    def _fallback_plan(self, *, question: str, constraints: list[str]) -> TaskPlan:
        complex_keywords = [
            "设计",
            "架构",
            "代码",
            "实现",
            "教程",
            "审查",
            "方案",
            "生成",
            "重构",
        ]
        is_complex = any(keyword in question for keyword in complex_keywords)

        if not is_complex:
            return TaskPlan(
                goal=question,
                complexity="simple",
                should_use_multi_agent=False,
                reason="问题较简单，不需要多角色协作",
                subtasks=[],
                constraints=constraints,
                success_criteria=["直接回答用户问题"],
                confidence=0.6,
            )

        return TaskPlan(
            goal=question,
            complexity="complex",
            should_use_multi_agent=True,
            reason="任务涉及工程设计或复杂产物，适合 research/coding/review 分工",
            constraints=constraints,
            success_criteria=[
                "事实依据清晰",
                "方案可落地",
                "通过审查",
                "不违反项目架构约束",
            ],
            subtasks=[
                SubTask(
                    id="research",
                    role="research",
                    title="检索和整理事实",
                    objective="查找当前项目相关代码、教程和约束",
                    expected_output="结构化研究报告",
                    priority=90,
                ),
                SubTask(
                    id="coding",
                    role="coding",
                    title="生成工程方案",
                    objective="基于研究报告给出目录、代码和接入方式",
                    depends_on=["research"],
                    expected_output="代码方案和实现说明",
                    priority=80,
                ),
                SubTask(
                    id="review",
                    role="review",
                    title="审查方案",
                    objective="检查方案是否符合项目约束和安全边界",
                    depends_on=["coding"],
                    expected_output="审查报告",
                    priority=70,
                ),
            ],
            confidence=0.75,
        )
