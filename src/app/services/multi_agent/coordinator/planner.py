from __future__ import annotations

from time import perf_counter

from src.app.config import resolve_llm_model
from src.app.services.llm.factory import get_llm_provider
from src.app.services.multi_agent.coordinator.decision_parser import (
    CoordinatorDecisionParser,
)
from src.app.services.multi_agent.coordinator.prompt_builder import (
    COORDINATOR_PROMPT_VERSION,
    CoordinatorPromptBuilder,
)
from src.app.services.multi_agent.coordinator.schemas import (
    CoordinatorDecision,
    CoordinatorGlobalState,
)


class CoordinatorPlanner:
    def __init__(self) -> None:
        self.llm_provider = get_llm_provider()
        self.prompt_builder = CoordinatorPromptBuilder()
        self.parser = CoordinatorDecisionParser()

    def plan(self, state: CoordinatorGlobalState) -> CoordinatorDecision:
        start = perf_counter()
        raw_content: str | None = None
        messages = self.prompt_builder.build_messages(state)
        model = resolve_llm_model(model=state.model)

        try:
            response = self.llm_provider.structured_chat(
                messages=messages,
                model=model,
                thinking_enabled=False,
            )
            raw_content = response.content
            decision = self.parser.parse(response.content)
            decision = self._validate_state_transition(state, decision)

            state.metadata.setdefault("coordinator_planner_events", []).append(
                {
                    "planner": "coordinator_llm",
                    "prompt_version": COORDINATOR_PROMPT_VERSION,
                    "model": response.model,
                    "provider": response.provider,
                    "latency_ms": int((perf_counter() - start) * 1000),
                    "decision": decision.model_dump(mode="json"),
                }
            )
            return decision

        except Exception as exc:
            state.metadata.setdefault("coordinator_planner_events", []).append(
                {
                    "planner": "coordinator_llm",
                    "fallback": True,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "raw_content": raw_content[:4000] if raw_content else None,
                    "latency_ms": int((perf_counter() - start) * 1000),
                }
            )
            return self._fallback_decision(state)

    def _validate_state_transition(
        self,
        state: CoordinatorGlobalState,
        decision: CoordinatorDecision,
    ) -> CoordinatorDecision:
        if decision.type in ("run_role", "revise_role", "request_review"):
            assert decision.role is not None

            if state.role_run_count(decision.role) >= state.max_same_role_runs:
                raise ValueError(
                    f"Role {decision.role} exceeded max_same_role_runs"
                )

            # 复杂代码任务不允许直接 review，没有 coding artifact 则 review 意义不大。
            if decision.role == "review":
                has_coding = any(item.get("role") == "coding" for item in state.artifacts)
                if not has_coding:
                    raise ValueError("Cannot run review before coding artifact exists")

            for artifact_id in decision.input_artifact_ids:
                if artifact_id not in state.artifact_ids():
                    raise ValueError(f"Unknown input_artifact_id: {artifact_id}")

        if decision.type == "revise_role":
            if state.revision_count >= state.max_revisions:
                raise ValueError("Exceeded max_revisions")

        if decision.type == "final":
            # 最低要求：至少有一个 artifact。
            if not state.artifacts:
                raise ValueError("Cannot final without artifacts")

        if decision.type == "fail":
            failure_text = " ".join(
                filter(None, [decision.failure_code, decision.failure_message])
            ).lower()
            if "max_same_role_runs" in failure_text:
                roles_with_capacity = [
                    role
                    for role in ("research", "coding", "review")
                    if state.role_run_count(role) < state.max_same_role_runs
                ]
                if roles_with_capacity:
                    counts = {
                        role: state.role_run_count(role)
                        for role in roles_with_capacity
                    }
                    raise ValueError(
                        "Coordinator reported a false max_same_role_runs limit: "
                        f"limit={state.max_same_role_runs}, counts={counts}"
                    )

        return decision

    def _fallback_decision(self, state: CoordinatorGlobalState) -> CoordinatorDecision:
        """保守 fallback：按当前状态选择最安全的下一步。"""

        has_research = any(item.get("role") == "research" for item in state.artifacts)
        has_coding = any(item.get("role") == "coding" for item in state.artifacts)
        has_review = any(item.get("role") == "review" for item in state.artifacts)

        if not has_research:
            return CoordinatorDecision(
                type="run_role",
                role="research",
                task_id="fallback_research",
                task_title="补充研究资料",
                task_objective="检索并整理和用户问题相关的事实、来源和未确认问题。",
                expected_output="research_report",
                reason="CoordinatorPlanner 失败，fallback 到 ResearchAgent 先收集事实。",
                confidence=0.35,
            )

        if not has_coding:
            return CoordinatorDecision(
                type="run_role",
                role="coding",
                task_id="fallback_coding",
                task_title="生成工程方案",
                task_objective="基于已有研究资料生成可落地的工程修改方案。",
                expected_output="coding_proposal",
                input_artifact_ids=[item["id"] for item in state.artifacts if item.get("role") == "research"],
                reason="CoordinatorPlanner 失败，fallback 到 CodingAgent 生成方案。",
                confidence=0.35,
            )

        if not has_review:
            return CoordinatorDecision(
                type="request_review",
                role="review",
                task_id="fallback_review",
                task_title="审查工程方案",
                task_objective="审查已有 coding_proposal 是否满足事实依据、项目约束和安全边界。",
                expected_output="review_report",
                input_artifact_ids=[item["id"] for item in state.artifacts],
                reason="CoordinatorPlanner 失败，fallback 到 ReviewAgent 审查。",
                confidence=0.35,
            )

        return CoordinatorDecision(
            type="final",
            reason="CoordinatorPlanner 失败，但已有 artifacts 足够进入最终汇总。",
            confidence=0.3,
            final_answer_instruction="请基于已有 artifacts 谨慎生成最终回答，并说明可能存在的不确定性。",
        )
