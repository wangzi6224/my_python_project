from __future__ import annotations

from time import perf_counter
from typing import Any

from src.app.services.multi_agent.agents.coding_agent import CodingAgent
from src.app.services.multi_agent.agents.research_agent import ResearchAgent
from src.app.services.multi_agent.agents.review_agent import ReviewAgent
from src.app.services.multi_agent.coordinator.planner import CoordinatorPlanner
from src.app.services.multi_agent.coordinator.schemas import (
    CoordinatorGlobalState,
    CoordinatorRound,
)
from src.app.services.multi_agent.handoff import HandoffBuilder
from src.app.services.multi_agent.role_runtime.schemas import AutonomousRoleState
from src.app.services.multi_agent.schemas import AgentArtifact, HandoffMessage, RoleRunResult
from src.app.services.multi_agent.store import MultiAgentStore


class MultiAgentCoordinatorLoop:
    """Level 3 全局动态 Multi-Agent Loop。"""

    def __init__(self) -> None:
        self.planner = CoordinatorPlanner()
        self.store = MultiAgentStore()
        self.research = ResearchAgent()
        self.coding = CodingAgent()
        self.review = ReviewAgent()
        self.handoff_builder = HandoffBuilder()

    def run(
        self,
        *,
        state: CoordinatorGlobalState,
        enable_mcp_tools: bool,
    ) -> CoordinatorGlobalState:
        for index in range(state.max_rounds):
            round_index = index + 1
            start = perf_counter()

            decision = self.planner.plan(state)
            round_item = CoordinatorRound(
                round_index=round_index,
                decision=decision,
                status="running",
            )
            state.rounds.append(round_item)

            try:
                if decision.type == "final":
                    round_item.status = "completed"
                    state.finish_reason = "coordinator_final"
                    break

                if decision.type == "fail":
                    round_item.status = "failed"
                    round_item.error_code = decision.failure_code or "COORDINATOR_FAIL"
                    round_item.error_message = decision.failure_message
                    state.finish_reason = "coordinator_fail"
                    break

                if decision.type == "skip_role":
                    if decision.target_role:
                        state.skipped_roles.append(decision.target_role)
                    round_item.status = "skipped"
                    continue

                if decision.type in ("run_role", "revise_role", "request_review"):
                    result = self._run_role(
                        global_state=state,
                        round_index=round_index,
                        enable_mcp_tools=enable_mcp_tools,
                    )

                    state.role_runs.append(
                        {
                            "role": result.role,
                            "status": result.status,
                            "latency_ms": result.latency_ms,
                            "artifact_id": result.artifact.id if result.artifact else None,
                            "trace": result.trace,
                        }
                    )

                    if result.artifact:
                        artifact_dict = result.artifact.model_dump(mode="json")
                        state.artifacts.append(artifact_dict)
                        round_item.artifact_id = result.artifact.id
                        self.store.create_artifact(
                            result.artifact,
                            multi_agent_run_id=state.multi_agent_run_id,
                        )

                        handoff = self._maybe_create_handoff(
                            global_state=state,
                            artifact=result.artifact,
                        )
                        if handoff:
                            state.handoffs.append(handoff.model_dump(mode="json"))
                            round_item.handoff_id = handoff.id
                            self.store.create_handoff(
                                handoff,
                                multi_agent_run_id=state.multi_agent_run_id,
                            )

                    state.tool_calls.extend(result.trace.get("tool_calls", []))
                    round_item.role_run_id = result.trace.get("role_run_id")
                    round_item.status = result.status

                    if decision.type == "revise_role":
                        state.revision_count += 1

                round_item.latency_ms = int((perf_counter() - start) * 1000)

            except Exception as exc:
                round_item.status = "failed"
                round_item.error_code = type(exc).__name__
                round_item.error_message = str(exc)
                round_item.latency_ms = int((perf_counter() - start) * 1000)
                state.failed_round_count += 1

                if state.failed_round_count >= state.max_failed_rounds:
                    state.finish_reason = "max_failed_rounds_reached"
                    break

        if state.finish_reason is None:
            state.finish_reason = "max_rounds_reached"

        return state

    def _run_role(
        self,
        *,
        global_state: CoordinatorGlobalState,
        round_index: int,
        enable_mcp_tools: bool,
    ) -> RoleRunResult:
        decision = global_state.rounds[-1].decision
        assert decision.role is not None

        role_state = AutonomousRoleState(
            multi_agent_run_id=global_state.multi_agent_run_id,
            coordinator_round_index=round_index,
            role=decision.role,
            conversation_id=global_state.conversation_id,
            user_message_id=global_state.user_message_id,
            question=global_state.question,
            model=global_state.model,
            task_id=decision.task_id,
            task_title=decision.task_title,
            task_objective=decision.task_objective or "",
            expected_output=decision.expected_output,
            constraints=global_state.initial_constraints + decision.constraints,
            input_artifacts=self._select_artifacts(global_state, decision.input_artifact_ids),
            input_handoffs=self._select_handoffs(global_state, decision.input_handoff_ids),
            review_feedback=decision.review_feedback,
            max_steps=global_state.max_role_steps,
            trace_id=global_state.trace_id,
            assistant_run_id=global_state.assistant_run_id,
            parent_span_id=global_state.parent_span_id,
        )

        agent = self._get_agent(decision.role)
        return agent.run_autonomous_with_timing(
            role_state=role_state,
            enable_mcp_tools=enable_mcp_tools,
        )

    def _get_agent(self, role: str):
        if role == "research":
            return self.research
        if role == "coding":
            return self.coding
        if role == "review":
            return self.review
        raise ValueError(f"Unsupported role for coordinator loop: {role}")

    def _select_artifacts(
        self,
        state: CoordinatorGlobalState,
        artifact_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not artifact_ids:
            return state.artifacts
        selected = []
        for artifact in state.artifacts:
            if artifact.get("id") in artifact_ids:
                selected.append(artifact)
        return selected

    def _select_handoffs(
        self,
        state: CoordinatorGlobalState,
        handoff_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not handoff_ids:
            return state.handoffs
        return [item for item in state.handoffs if item.get("id") in handoff_ids]

    def _maybe_create_handoff(
        self,
        *,
        global_state: CoordinatorGlobalState,
        artifact: AgentArtifact,
    ) -> HandoffMessage | None:
        # Level 3 中 handoff 不是固定 research->coding。
        # 第一版采用保守策略：只有 Coordinator 下一轮会决定真实 to_role，
        # 所以这里可以先不生成，或者生成 to_role=review/coding 的建议。
        return None
